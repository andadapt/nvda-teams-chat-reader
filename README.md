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

- Control+Alt+L: in the calendar, list the events in the view that is open, such as this work week. Each day is its own section with the number of events, and below it each event's time, title and organiser. Arrow up and down to move through the list, press Enter to go to that event in the calendar, or Escape to close the list.

You can change these keys in NVDA's Input Gestures dialog, under the "Teams Chat Reader" category.

## Debugging commands

These help when reporting a problem. They write to the NVDA log, which you can open from the NVDA menu under Tools, View log.

- NVDA+Alt+Shift+D: capture what NVDA sees of the Teams window: the focused element, everything around it, and up to 4000 elements of the page. NVDA may be silent for a few seconds while it works and says how many elements it captured.
- NVDA+Alt+Shift+F: turn focus logging on or off. While it is on, every element you move to in Teams is written to the log, with where it sits on the page. It turns off again when NVDA restarts.

The log then contains the text of your chats, calendar events and anything else on screen. Read it and remove anything private before you share it.

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
