# Teams Chat Reader
# Alt+1 reads the most recent message in the open Teams chat, Alt+2 the one before, up to Alt+0 for the tenth.
# Pressing the same key twice quickly copies that message to the clipboard.

import time

import api
import controlTypes
import globalPluginHandler
import ui
from logHandler import log
from scriptHandler import getLastScriptRepeatCount, script

# Executable names for new Teams (ms-teams.exe) and classic Teams (teams.exe).
TEAMS_APP_NAMES = ("ms-teams", "teams")
TEAMS_WINDOW_CLASS = "TeamsWebView"

# HTML ids Teams puts on the chat area and on each message.
MESSAGE_PANE_ID = "message-pane-layout-a11y"
MESSAGE_BODY_PREFIX = "message-body-"
MESSAGE_CONTENT_PREFIX = "content-"

# Guards against walking forever if the page is unexpectedly large.
MAX_SEARCH_NODES = 5000


def getHtmlId(obj):
	"""The HTML id of a web element, whether NVDA reaches it through IAccessible2 or UI Automation.
	Each lookup is a call into the Teams process, so the result is remembered on the object."""
	cached = getattr(obj, "_teamsChatReaderHtmlId", None)
	if cached is not None:
		return cached
	htmlId = ""
	try:
		attrs = obj.IA2Attributes
		if attrs and attrs.get("id"):
			htmlId = attrs["id"]
	except Exception:
		pass
	if not htmlId:
		try:
			htmlId = obj.UIAAutomationId or ""
		except Exception:
			pass
	try:
		obj._teamsChatReaderHtmlId = htmlId
	except Exception:
		pass
	return htmlId


def findDescendant(start, predicate, reverse=False, skip=None):
	"""Depth-first search below start. With reverse=True, the last element in the document is checked first."""
	visited = 0
	stack = []
	child = start.lastChild if reverse else start.firstChild
	while child:
		stack.append(child)
		child = child.previous if reverse else child.next
	stack.reverse()
	while stack:
		obj = stack.pop()
		visited += 1
		if visited > MAX_SEARCH_NODES:
			return None
		if predicate(obj):
			return obj
		if skip and skip(obj):
			continue
		kids = []
		child = obj.lastChild if reverse else obj.firstChild
		while child:
			kids.append(child)
			child = child.previous if reverse else child.next
		stack.extend(reversed(kids))
	return None


def isInTeams():
	fg = api.getForegroundObject()
	if not fg:
		return False
	appName = getattr(fg.appModule, "appName", "")
	return appName in TEAMS_APP_NAMES or fg.windowClassName == TEAMS_WINDOW_CLASS


def getTeamsDocument():
	"""The web document holding the Teams interface."""
	obj = api.getFocusObject()
	while obj:
		if obj.role == controlTypes.Role.DOCUMENT:
			return obj
		obj = obj.parent
	# Focus is outside the web content, so search down from the window instead.
	fg = api.getForegroundObject()
	if fg:
		return findDescendant(fg, lambda o: o.role == controlTypes.Role.DOCUMENT)
	return None


# The message pane found by the last search; Teams usually keeps it alive between key presses.
_cachedPane = None

# Roles that never contain the message pane, so the search doesn't look inside them.
_PANE_SEARCH_SKIP_ROLES = (
	controlTypes.Role.TREEVIEW,
	controlTypes.Role.LIST,
	controlTypes.Role.TOOLBAR,
	controlTypes.Role.BUTTON,
	controlTypes.Role.COMBOBOX,
)


# Roles in the message pane that hold controls rather than messages.
_MESSAGE_SEARCH_SKIP_ROLES = (
	controlTypes.Role.EDITABLETEXT,
	controlTypes.Role.TOOLBAR,
	controlTypes.Role.BUTTON,
)


def isPaneAlive(pane):
	try:
		return pane.parent is not None and getHtmlId(pane) == MESSAGE_PANE_ID
	except Exception:
		return False


def getMessagePane():
	global _cachedPane
	if _cachedPane and isPaneAlive(_cachedPane):
		return _cachedPane
	# The message box and message list are inside the pane, so check what contains the focus first.
	obj = api.getFocusObject()
	while obj and obj.role != controlTypes.Role.DOCUMENT:
		if getHtmlId(obj) == MESSAGE_PANE_ID:
			_cachedPane = obj
			return obj
		obj = obj.parent
	doc = getTeamsDocument()
	if not doc:
		return None
	_cachedPane = findDescendant(
		doc,
		lambda o: getHtmlId(o) == MESSAGE_PANE_ID,
		skip=lambda o: o.role in _PANE_SEARCH_SKIP_ROLES,
	)
	return _cachedPane


# The element whose children are the messages, found from the first message located.
_cachedMessageContainer = None
# Set when a whole-pane search found no messages outside the cached container.
_confirmedCompleteContainer = None


def isMessageBody(obj):
	return getHtmlId(obj).startswith(MESSAGE_BODY_PREFIX)


def skipWhenSearchingForMessages(obj):
	"""Don't look inside a message for another one, or inside the message box and its toolbars."""
	return obj.role in _MESSAGE_SEARCH_SKIP_ROLES or isMessageBody(obj)


def collectMessages(root, count):
	"""Up to count messages below root, most recent first. Searching backwards visits the newest first."""
	messages = []

	def collect(obj):
		if isMessageBody(obj):
			messages.append(obj)
			return len(messages) >= count
		return False

	# collect() returns True once enough are found, which ends the search.
	findDescendant(root, collect, reverse=True, skip=skipWhenSearchingForMessages)
	return messages


def findWiderContainer(container, pane):
	"""If a message sits after the container, the container is too narrow (for example one person's group
	of messages, with a reply from someone else after it). Return the ancestor that holds both, or None.
	The check stops below the pane: past the message list there is only the message box, which never holds
	messages and is slow to search."""
	obj = container
	while obj is not None and obj != pane and obj.parent != pane:
		sibling = obj.next
		while sibling:
			if isMessageBody(sibling) or findDescendant(sibling, isMessageBody, skip=skipWhenSearchingForMessages):
				return obj.parent
			sibling = sibling.next
		obj = obj.parent
	return None


def getAncestors(obj, stop):
	"""obj's parents from nearest upwards, ending at stop."""
	ancestors = []
	obj = obj.parent
	while obj:
		ancestors.append(obj)
		if obj == stop:
			break
		obj = obj.parent
	return ancestors


def findCommonAncestor(first, second, stop):
	firstAncestors = getAncestors(first, stop)
	for obj in getAncestors(second, stop):
		if obj in firstAncestors:
			return obj
	return None


def getMessagesFromCachedContainer(pane, count):
	"""Messages from the remembered container, widening it first if a newer message sits outside it.
	Returns (messages, trusted). trusted is False when the container holds too few and the whole pane must be
	searched; messages is None when there is no usable container."""
	global _cachedMessageContainer, _confirmedCompleteContainer
	container = _cachedMessageContainer
	# The container must still be inside the current pane: one left over from another chat would read the wrong
	# messages, and the widening check would climb past the pane to the top of the tree.
	if container is None or pane not in getAncestors(container, pane):
		return None, False
	start = time.perf_counter()
	widened = False
	wider = findWiderContainer(container, pane)
	while wider is not None:
		container = wider
		widened = True
		wider = findWiderContainer(container, pane)
	checkTime = time.perf_counter()
	_cachedMessageContainer = container
	messages = collectMessages(container, count)
	log.debug("Teams Chat Reader timing: safety check {:.0f} ms{}, {} messages from cached container {:.0f} ms".format(
		(checkTime - start) * 1000, " (widened container)" if widened else "",
		len(messages), (time.perf_counter() - checkTime) * 1000))
	# Too few means older messages may sit outside the container, so search the whole pane,
	# unless a whole-pane search already found nothing beyond what the container holds.
	trusted = len(messages) == count or (
		_confirmedCompleteContainer is not None and container == _confirmedCompleteContainer
	)
	return messages, trusted


def getRecentMessages(count):
	"""Up to count message objects, most recent first."""
	global _cachedMessageContainer, _confirmedCompleteContainer
	start = time.perf_counter()
	pane = getMessagePane()
	paneTime = time.perf_counter()
	if not pane:
		return None
	try:
		containerMessages, trusted = getMessagesFromCachedContainer(pane, count)
	except Exception:
		# The remembered container has gone, for example after switching chats.
		_cachedMessageContainer = None
		containerMessages, trusted = None, False
	if trusted:
		return containerMessages
	if containerMessages is None:
		_cachedMessageContainer = None
	# At least two messages are needed to work out which element holds them all.
	messages = collectMessages(pane, max(count, 2))
	if containerMessages is not None:
		if len(messages[:count]) <= len(containerMessages):
			_confirmedCompleteContainer = _cachedMessageContainer
	elif len(messages) >= 2:
		_cachedMessageContainer = findCommonAncestor(messages[0], messages[1], pane)
	log.debug("Teams Chat Reader timing: find pane {:.0f} ms, search whole pane for {} messages {:.0f} ms".format(
		(paneTime - start) * 1000, len(messages), (time.perf_counter() - paneTime) * 1000))
	return messages[:count]


def getVisibleText(obj):
	parts = []
	findDescendant(obj, lambda o: bool(o.role == controlTypes.Role.STATICTEXT and o.name and parts.append(o.name)))
	return " ".join(parts)


def getMessageContent(message):
	"""Just what was written, without the author and time."""
	msgId = getHtmlId(message)[len(MESSAGE_BODY_PREFIX):]
	content = findDescendant(message, lambda o: getHtmlId(o) == MESSAGE_CONTENT_PREFIX + msgId)
	if content:
		return content.name or getVisibleText(content)
	return ""


def getMessageText(message):
	"""Teams labels each message with author, text and time; fall back to the visible text."""
	return message.name or getMessageContent(message) or getVisibleText(message)


class GlobalPlugin(globalPluginHandler.GlobalPlugin):

	def getScript(self, gesture):
		# Only claim Alt+number while Teams is in front, so other apps keep their own shortcuts.
		if not isInTeams():
			return None
		return super().getScript(gesture)

	# The message the last press read, so a second press can copy it without searching again.
	_lastMessage = None
	# The key of the last press. NVDA counts any quick repeat of this script as a double press, even with a
	# different number key, so a copy only happens when the same key was pressed twice.
	_lastKey = None

	def _readMessage(self, position):
		self._lastMessage = None
		try:
			messages = getRecentMessages(position)
		except Exception:
			log.error("Teams Chat Reader: failed to read messages", exc_info=True)
			ui.message("Could not read messages")
			return
		if messages is None:
			ui.message("No chat open")
			return
		if len(messages) < position:
			ui.message("No message {}".format(position))
			return
		self._lastMessage = messages[position - 1]
		ui.message(getMessageText(self._lastMessage))

	def _copyLastMessage(self):
		if self._lastMessage is None:
			return
		try:
			text = getMessageContent(self._lastMessage) or getMessageText(self._lastMessage)
		except Exception:
			log.error("Teams Chat Reader: failed to copy message", exc_info=True)
			text = ""
		if text and api.copyToClip(text):
			ui.message("Copied")
		else:
			ui.message("Could not copy message")

	@script(
		description=(
			"Teams: read the message at the position given by the number key (1 is the most recent, 0 is the tenth). "
			"Press twice to copy it to the clipboard"
		),
		category="Teams Chat Reader",
		gestures=["kb:alt+{}".format(n) for n in "1234567890"],
	)
	def script_readRecentMessage(self, gesture):
		key = gesture.mainKeyName
		if getLastScriptRepeatCount() == 1 and key == self._lastKey:
			self._copyLastMessage()
			return
		self._lastKey = key
		self._readMessage(10 if key == "0" else int(key))
