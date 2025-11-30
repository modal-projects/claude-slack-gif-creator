import os
import re
import tempfile
from pathlib import Path

import modal

app = modal.App("slack-gif-creator")

slack_secret = modal.Secret.from_name("claude-code-slackbot-secret")  # SLACK_BOT_TOKEN, SLACK_SIGNING_SECRET
anthropic_secret = modal.Secret.from_name("anthropic-secret")  # ANTHROPIC_API_KEY

vol = modal.Volume.from_name("gif-workspace", create_if_missing=True)

# Path to agent_entrypoint.py (same directory as this file)
AGENT_ENTRYPOINT = Path(__file__).parent / "agent"

DEBUG_TOOL_USE = True

VOL_MOUNT_PATH = Path("/workspace")

sandbox_image = (
    modal.Image.debian_slim(python_version="3.12")
    .apt_install("git")
    .pip_install("claude-agent-sdk", "slack-sdk")
    .run_commands(
        # Clone skill from GitHub
        "git clone --depth 1 --filter=blob:none --sparse https://github.com/anthropics/skills.git /tmp/skills-repo",
        "cd /tmp/skills-repo && git sparse-checkout set slack-gif-creator",
        # Set up skill for SDK discovery at /app/.claude/skills/
        "mkdir -p /app/.claude/skills",
        "mv /tmp/skills-repo/slack-gif-creator /app/.claude/skills/slack_gif_creator",
        "rm -rf /tmp/skills-repo",
    )
    .run_commands("pip install -r /app/.claude/skills/slack_gif_creator/requirements.txt")
    .pip_install("rembg[cpu,cli]", "sniffio")
    .run_commands("rembg d u2net_human_seg") # download and save the model.
    .add_local_dir(AGENT_ENTRYPOINT, "/agent")

)

slack_bot_image = modal.Image.debian_slim(python_version="3.12").pip_install(
    "slack-bolt", "fastapi"
)


def download_slack_file(url: str, token: str) -> bytes:
    """Download a file from Slack using the bot token for authentication."""
    import urllib.request
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
    with urllib.request.urlopen(req) as response:
        return response.read()


def upload_images_to_sandbox(sb: modal.Sandbox, files: list, token: str) -> list[str]:
    """Download images from Slack and upload them to the sandbox."""
    image_types = {"png", "jpg", "jpeg", "gif", "webp", "bmp"}
    uploaded = []

    for file_info in files:
        filetype = file_info.get("filetype", "").lower()
        if filetype not in image_types:
            continue

        url = file_info.get("url_private")
        name = file_info.get("name", f"image.{filetype}")
        if not url:
            continue

        image_data = download_slack_file(url, token)
        dest_path = f"/data/{name}"

        with sb.open(dest_path, "wb") as sb_file:
            sb_file.write(image_data)

        uploaded.append(dest_path)

    return uploaded


def run_claude_turn(sb: modal.Sandbox, user_message: str, channel: str, thread_ts: str, sandbox_name: str) -> dict:
    """Execute one turn of Claude conversation in sandbox using ClaudeSDKClient."""
    args = ["python", "/agent/agent_entrypoint.py", "--message", user_message, "--sandbox-name", sandbox_name]

    if DEBUG_TOOL_USE:
        args.extend(["--channel", channel, "--thread-ts", thread_ts])

    process = sb.exec(*args)

    for line in process.stdout:
        yield {"response": line}

    exit_code = process.wait()

    print(f"Process exited with status {exit_code}")

    stderr = process.stderr.read()
    if stderr:
        yield {"response": f"*** ERROR ***\n{stderr}"}

    # Check for generated GIF
    gif_check = sb.exec("test", "-f", "/data/output.gif")
    gif_exists = gif_check.wait() == 0

    if gif_exists:
        with sb.open("/data/output.gif", "rb") as f:
            gif_data = f.read()

        # Save locally for upload (use unique name to avoid conflicts)
        with tempfile.NamedTemporaryFile(suffix=".gif", delete=False) as f:
            f.write(gif_data)
            gif_path = f.name
        yield {"gif_path": gif_path}
    else:
        yield {"response": "No GIF generated"}


@app.function(secrets=[slack_secret], image=slack_bot_image, scaledown_window=10 * 60, min_containers=1)
@modal.concurrent(max_inputs=100)
@modal.asgi_app()
def slack_bot():
    from fastapi import FastAPI, Request
    from slack_bolt import App as SlackApp
    from slack_bolt.adapter.fastapi import SlackRequestHandler

    slack_app = SlackApp(
        token=os.environ["SLACK_BOT_TOKEN"],
        signing_secret=os.environ["SLACK_SIGNING_SECRET"],
    )

    fastapi_app = FastAPI()
    handler = SlackRequestHandler(slack_app)

    def process_message(body, client, user_message, files):
        """Common logic for processing messages (mentions and thread replies)."""
        channel = body["event"]["channel"]
        thread_ts = body["event"].get("thread_ts", body["event"]["ts"])

        sandbox_name = f"gif-{body['team_id']}-{thread_ts}".replace(".", "-")

        try:
            sb = modal.Sandbox.from_name(app_name=app.name, name=sandbox_name)
        except modal.exception.NotFoundError:
            sb = modal.Sandbox.create(
                app=app,
                image=sandbox_image,
                secrets=[anthropic_secret] + ([slack_secret] if DEBUG_TOOL_USE else []),
                volumes={VOL_MOUNT_PATH: vol},
                workdir="/app",
                env={"CLAUDE_CONFIG_DIR": VOL_MOUNT_PATH.as_posix() + "/claude-config"},
                idle_timeout=20 * 60,
                timeout=5 * 60 * 60,
                name=sandbox_name,
            )

        data_dir = (VOL_MOUNT_PATH / sandbox_name).as_posix()
        sb.exec("bash", "-c", f"mkdir -p {data_dir} && ln -s {data_dir} /data")

        if files:
            uploaded = upload_images_to_sandbox(sb, files, os.environ["SLACK_BOT_TOKEN"])
            if uploaded:
                user_message += f"\n\nUploaded images: {', '.join(uploaded)}"

        for result in run_claude_turn(sb, user_message, channel, thread_ts, sandbox_name):
            if result.get("response"):
                client.chat_postMessage(
                    channel=channel, text=result["response"], thread_ts=thread_ts
                )

            if result.get("gif_path"):
                client.files_upload_v2(
                    channel=channel,
                    file=result["gif_path"],
                    thread_ts=thread_ts,
                    title="Generated Emoji GIF",
                )

    @slack_app.event("app_mention")
    def handle_mention(body, client, context, logger):
        user_message = body["event"]["text"]
        user_message = re.sub(r"<@[A-Z0-9]+>", "", user_message).strip()
        files = body["event"].get("files", [])
        process_message(body, client, user_message, files)

    @slack_app.event("message")
    def handle_message(body, client, context, logger):
        event = body["event"]
        if event.get("subtype") == "bot_message" or event.get("bot_id"):
            return
        if "thread_ts" not in event:
            return
        if f"<@{context.bot_user_id}>" in event.get("text", ""):
            return

        user_message = event["text"]
        files = event.get("files", [])
        process_message(body, client, user_message, files)

    @fastapi_app.post("/")
    async def root(request: Request):
        return await handler.handle(request)

    return fastapi_app
