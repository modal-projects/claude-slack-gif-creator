#!/usr/bin/env python3
"""Entrypoint script for Claude Agent SDK inside Modal sandbox."""

import argparse
import asyncio
import json
from pathlib import Path

from claude_agent_sdk import ClaudeAgentOptions, ClaudeSDKClient, HookMatcher, ResultMessage
from slack_tool_logger import SlackLogger

SESSIONS_FILE = Path("/data/sessions.json")


SYSTEM_PROMPT = """You are a Slack emoji GIF creator.

Always output 128x128 emoji-optimized GIFs. Save files to /data/output.gif. DO NOT USE ANY OTHER FILENAME.

Always use the slack_gif_creator skill that you have access to.

Additional instructions:

## Composition

Since the output will be small, try to make subjects bigger and in the center of the image.

## Image size

For uploaded images, always check the image size and resize if necessary to 512x512 or below,
*before* calling the Read tool on it. DO NOT try to read the image before the size is checked,
or the agent will crash.

## Background removal

If background removal is requested, use the `rembg` tool to remove the background.
`rembg` is installed in the sandbox image, along with the u2net_human_seg model.

Example:
```python
from rembg import remove, new_session
from PIL import Image

session = new_session("u2net_human_seg")

with Image.open("input.png") as input_img:
    result = remove(input_img, session=session)

result.save("output.png")
```

For transparent images, use `disposal=2` with `imageio` instead of GIFBuilder:

```python
frames = []
frames.append(frame)

imageio.mimsave(
    '/data/output.gif',
    frames,
    format='GIF',
    duration=1000/15,  # 15 fps
    loop=0,
    disposal=2  # This is the key parameter!
)
```
"""


def load_session_id(sandbox_name: str) -> str | None:
    """Load existing session ID for this sandbox/thread."""
    if not SESSIONS_FILE.exists():
        return None
    sessions = json.loads(SESSIONS_FILE.read_text())
    return sessions.get(sandbox_name)


def save_session_id(sandbox_name: str, session_id: str) -> None:
    """Save session ID for this sandbox/thread."""
    sessions = {}
    if SESSIONS_FILE.exists():
        sessions = json.loads(SESSIONS_FILE.read_text())
    sessions[sandbox_name] = session_id
    SESSIONS_FILE.write_text(json.dumps(sessions, indent=2))



async def main(user_msg: str, sandbox_name: str, channel: str, thread_ts: str):
    if channel and thread_ts:
        logger = SlackLogger(channel, thread_ts)
        hooks = {
            "PreToolUse": [HookMatcher(hooks=[logger.log_tool_use])],
            "PostToolUse": [HookMatcher(hooks=[logger.log_tool_use])],
        }
    else:
        hooks = None

    session_id = load_session_id(sandbox_name)

    options = ClaudeAgentOptions(
        resume=session_id,
        system_prompt=SYSTEM_PROMPT,
        cwd="/app",  # Skills are discovered from /app/.claude/skills/
        setting_sources=["project"],
        allowed_tools=["Skill", "Read", "Write", "Bash"],
        permission_mode="acceptEdits",
        max_turns=10,
        hooks=hooks,
    )

    async with ClaudeSDKClient(options=options) as client:
        await client.query(user_msg)

        async for msg in client.receive_response():
            if isinstance(msg, ResultMessage):
                save_session_id(sandbox_name, msg.session_id)
            elif hasattr(msg, "content"):
                for block in msg.content:
                    if hasattr(block, "text"):
                        print(block.text)
        print("Exiting...")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--message", type=str, required=True)
    parser.add_argument("--sandbox-name", type=str, required=True)
    parser.add_argument("--channel", type=str, required=False)
    parser.add_argument("--thread-ts", type=str, required=False)
    args = parser.parse_args()

    asyncio.run(main(args.message, args.sandbox_name, args.channel, args.thread_ts))
