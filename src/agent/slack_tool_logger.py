import os
import re
from typing import Any

import slack_sdk
from claude_agent_sdk import HookContext

HEREDOC_PATTERN = re.compile(
    r"<<-?\s*(?:(?P<quote>['\"])(?P<quoted_label>[\w-]+)(?P=quote)|\\?(?P<simple_label>[\w-]+))"
)


class SlackLogger:
    slack_client = None
    channel: str
    thread_ts: str

    def __init__(self, channel: str, thread_ts: str):
        self.slack_client = slack_sdk.WebClient(token=os.environ["SLACK_BOT_TOKEN"])
        self.channel = channel
        self.thread_ts = thread_ts

    async def log_tool_use(
        self, input_data: dict[str, Any], tool_use_id: str | None, context: HookContext
    ) -> dict[str, Any]:
        if "tool_response" in input_data:
            # Format tool response
            input_data["tool_response"].pop("command", None)
            input_data["tool_response"].pop("content", None)
            input_data["tool_response"].pop("file_path", None)

            response_str = str(input_data["tool_response"])

            # Truncate if too long
            if len(response_str) > 500:
                response_str = response_str[:500] + "..."

            message = f"🔧 *Tool Response:*\n```\n{response_str}\n```"
            self.slack_client.chat_postMessage(
                channel=self.channel,
                text=message,
                thread_ts=self.thread_ts,
                mrkdwn=True,
            )
        elif "tool_input" in input_data:
            # Format tool input with tool name
            tool_name = input_data.get("tool_name", "Unknown Tool")
            tool_input = input_data["tool_input"]
            input_str = str(tool_input)

            # Check if tool_input is a dict with a 'command' field containing a heredoc
            if "command" in tool_input:
                content, filename = self._extract_file_write_content(tool_input["command"])
            elif "content" in tool_input:
                content = tool_input["content"]
                filename = os.path.basename(tool_input["file_path"])
            else:
                content = None
                filename = None

            if content:
                try:
                    self.slack_client.files_upload_v2(
                        channel=self.channel,
                        content=content,
                        filename=filename,
                        title=f"Generated {filename}",
                        thread_ts=self.thread_ts,
                        initial_comment="⚙️ *Using Tool:* file write",
                    )
                    return {}
                except Exception as e:
                    print(f"Error uploading heredoc content: {e}")

            # Truncate if too long
            if len(input_str) > 500:
                input_str = input_str[:500] + "..."

            message = f"⚙️ *Using Tool:* `{tool_name}`\n```\n{input_str}\n```"
            self.slack_client.chat_postMessage(
                channel=self.channel,
                text=message,
                thread_ts=self.thread_ts,
                mrkdwn=True,
            )
        return {}

    @staticmethod
    def _extract_file_write_content(command: str) -> tuple[str | None, str | None]:
        match = HEREDOC_PATTERN.search(command)
        if not match:
            return None, None

        label = match.group("quoted_label") or match.group("simple_label")

        newline_after_marker = command.find("\n", match.end())
        if newline_after_marker == -1:
            return None, None
        content_start = newline_after_marker + 1
        closing_pattern = re.compile(rf"(?m)^\s*{re.escape(label)}\s*$")
        closing_match = closing_pattern.search(command, pos=content_start)
        if not closing_match:
            return None, None
        snippet_content = command[content_start : closing_match.start()]
        filename = SlackLogger._infer_filename_from_command(
            command, label
        )
        return snippet_content, filename

    @staticmethod
    def _infer_filename_from_command(command: str, default_label: str) -> str:
        redirect_match = re.search(r">\s*([^\s]+)", command)
        if redirect_match:
            candidate = redirect_match.group(1).strip("'\"")
            if candidate:
                return os.path.basename(candidate)
        return f"{default_label.lower()}_heredoc.txt"
