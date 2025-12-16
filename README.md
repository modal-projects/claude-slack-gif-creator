# Claude Slack GIF Creator

![](./assets/claude-pelican-bicycle.gif)
![](./assets/agi-party.gif)
![](./assets/gongy-ships.gif)

A bot powered by Claude that creates custom Slackmoji-ready GIFs.

Or, in GIF form:

![A bot powered by Claude that creates custom Slackmoji-ready GIFs](./assets/claude-gif-gif.gif)

The bot runs on [Modal](https://modal.com/) and uses the [Claude Agent SDK](https://platform.claude.com/docs/en/agent-sdk/overview)
with the [`slack-gif-creator` skill from Anthropic](https://github.com/anthropics/skills/blob/main/skills/slack-gif-creator/SKILL.md).

## Features

- **Natural Language GIF Generation**: Describe what you want and Claude will create a 128x128 emoji-optimized GIF
- **Thread-Based Conversations**: Each Slack thread maintains its own conversation context, stored on Modal
- **Image Upload Support**: Upload images to the bot to incorporate them into your GIFs
- **Background Removal**: Backgrounds removed using the `rembg` tool, so you can make GIFs of your friends
- **Real-time Tool Logging**: See Claude's tool usage in the Slack thread as it works

## Architecture

The bot consists of three main components:

1. **Slack Bot** (`src/main.py`): Handles Slack events (mentions and thread replies) and manages [Modal Sandboxes](https://modal.com/docs/guide/sandbox)
2. **Claude Agent** (`src/agent/agent_entrypoint.py`): Runs inside Modal Sandboxes and executes Claude with the GIF creation skill
3. **Anthropic API Proxy** (`src/proxy.py`): Proxies requests to the Anthropic API. This keeps the API key out of the Sandbox, so that Claude can't leak your API key when a naughty prompt hacker asks for a GIF containing it

Each Slack thread gets its own persistent [Modal Sandbox](https://modal.com/docs/guide/sandbox) with a dedicated [Volume](https://modal.com/docs/guide/volumes) for storing generated GIFs and session data.

## Prerequisites

- Python 3.10 or higher
- A [Modal](https://modal.com/) account
- A Slack workspace
- An Anthropic API key

## Setup

### 1. Install Dependencies

```bash
pip install modal
```

That's it!

If you've never used Modal before on this machine, also run

```bash
modal setup
```

### 2. Configure Slack App

[Create a new Slack app](https://api.slack.com/apps) in your workspace.

Your Slack app needs:

[**OAuth Scopes**](https://api.slack.com/scopes)
- `app_mentions:read`
- `chat:write`
- `files:read`
- `files:write`
- `channels:history`
- `groups:history`
- `im:history`
- `mpim:history`

[**Event Subscriptions**](https://api.slack.com/apis/connections/events-api):
- `app_mention`
- `message.channels`
- `message.groups`
- `message.im`
- `message.mpim`

### 3. Configure Modal Secrets

Create two Modal [Secrets](https://modal.com/docs/guide/secrets):

**anthropic-secret** with:
- `ANTHROPIC_API_KEY`: Your Anthropic API key

**claude-code-slackbot-secret** with:
- `SLACK_BOT_TOKEN`: Your [Slack bot token](https://api.slack.com/authentication/token-types#bot) (starts with `xoxb-`)
- `SLACK_SIGNING_SECRET`: Your Slack app's [signing secret](https://api.slack.com/authentication/verifying-requests-from-slack#about)


### 4. Deploy to Modal

```bash
modal deploy src/main.py
```

After deployment, Modal will provide a webhook URL. Add this URL to your Slack app's [Event Subscriptions Request URL](https://api.slack.com/apis/connections/events-api#the-events-api__subscribing-to-event-types__events-api-request-urls).

Finally, [install the app to your workspace](https://api.slack.com/start/quickstart#installing) and invite the bot to the channels where you want to use it.

## Usage

### Mention the Bot

Mention the bot in any channel with a description of the GIF you want:

> @GIFBot create a GIF of a pelican riding a bicycle

![](./assets/claude-pelican-bicycle.gif)

### Upload Images

Attach images to your message for the bot to incorporate:

> @GIFBot make a party GIF of this entity that flashes "AGI"

> [attach image]

![](./assets/agi-party.gif)


### Background Removal

Request background removal for transparent GIFs:

> @GIFBot make a GIF of this guy riding on a boat

> [attach image with background]

![](./assets/gongy-ships.gif)

### Thread Replies

Reply to the bot's messages in a thread to continue the conversation:

> @GIFBot make a GIF showing "A bot powered by Claude that creates custom Slackmoji-ready GIFs." on a screen

> the text runs off the screen, fix the wrapping

![](./assets/claude-gif-gif.gif)

## How It Works

1. User mentions the bot or replies in a thread
2. Slack sends an event to the Modal webhook
3. The bot creates or resumes a Modal sandbox for that thread
4. Images attached to the message are downloaded and uploaded to the sandbox
5. Claude Agent SDK runs inside the sandbox with the user's message
6. Claude uses the `slack-gif-creator` skill to generate the GIF
7. The generated GIF is uploaded back to the Slack thread
8. The sandbox remains alive for 20 minutes for follow-up requests

## Development

### Local Development

You can test the agent without the Slack integration by running it in a Modal Sandbox:

```bash
modal run src/main.py
```

### Debug Mode

Set `DEBUG_TOOL_USE = True` in `src/main.py:20` to enable real-time tool logging in Slack threads.

## Resources

- [Modal Documentation](https://modal.com/docs)
- [Claude Agent SDK](https://github.com/anthropics/anthropic-sdk-python)
- [Slack API Documentation](https://api.slack.com/)
- [Slack Bolt Framework](https://slack.dev/bolt-python/)
- [Building Slack Apps](https://api.slack.com/start)
- [slack-gif-creator Skill](https://github.com/anthropics/skills/tree/main/slack-gif-creator)
