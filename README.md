# Teams Chat Reader for NVDA

An NVDA add-on for the new Microsoft Teams. While you are in a chat, read recent messages with a single key press, without moving focus away from where you are typing.

## Download

[Download Teams Chat Reader (latest version)](https://github.com/andadapt/nvda-teams-chat-reader/releases/latest/download/teamsChatReader.nvda-addon)

Open the downloaded file and NVDA will offer to install it. Restart NVDA when asked.

## Keyboard commands

These work while Microsoft Teams is the active window. In other programs the keys behave as normal.

- Alt+1: read the most recent message in the open chat.
- Alt+2: read the message before that, and so on up to Alt+9.
- Alt+0: read the tenth most recent message.
- Press any of these twice quickly to copy that message's text to the clipboard.

You can change these keys in NVDA's Input Gestures dialog, under the "Teams Chat Reader" category.

## Requirements

- NVDA 2024.1 or later.
- The new Microsoft Teams (ms-teams.exe).

## Building from source

With Python installed, run this from the repository folder:

```
python build.py
```

The add-on is written to `dist\teamsChatReader.nvda-addon`.

## What's new

See the [changelog](CHANGELOG.md) for what changed in each version.

## Feedback

Please report problems or ideas on the [issues page](https://github.com/andadapt/nvda-teams-chat-reader/issues).
