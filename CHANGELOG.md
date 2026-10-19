# Changelog

## 0.3.0

- The commands now live in an app module for Teams, the standard NVDA way for app-specific add-ons. NVDA only offers them while Teams has focus, so the add-on no longer checks the foreground window on every key press.
- New Teams also gets NVDA's built-in Teams fix, which stops message menus from taking focus away from the message you are on.
- If you changed the Alt+number keys in Input Gestures, set them again: they now appear under "Teams Chat Reader" only when you open Input Gestures from Teams.

## 0.2.0

- Pressing two different Alt+number keys quickly, such as Alt+1 then Alt+2, now reads both messages. Before, the second press copied the first message instead. A message is now only copied when the same key is pressed twice.
- After switching chats, the add-on no longer risks reading messages from the previous chat or freezing NVDA while it searches.
- Version numbers now use the major.minor.patch format the NVDA Add-on Store expects.

## 0.1

- First release. In a Teams chat, Alt+1 reads the most recent message, Alt+2 the one before, up to Alt+0 for the tenth. Press a key twice to copy that message to the clipboard.
