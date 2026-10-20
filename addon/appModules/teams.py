# Teams Chat Reader
# Alt+1 reads the most recent message in the open Teams chat, Alt+2 the one before, up to Alt+0 for the tenth.
# Pressing the same key twice quickly copies that message to the clipboard.
# NVDA loads this module for classic Teams (teams.exe) by name; the global plugin maps new Teams (ms-teams.exe) to it.
# Teams draws its interface in Edge WebView2, and NVDA gives that content the app module of the process hosting it.

import time

import api
import controlTypes
import ui
from logHandler import log
from nvdaBuiltin.appModules.teams import AppModule as BuiltinTeamsAppModule
from scriptHandler import getLastScriptRepeatCount, script

# HTML ids Teams puts on the chat area and on each message.
MESSAGE_PANE_ID = "message-pane-layout-a11y"
MESSAGE_BODY_PREFIX = "message-body-"
MESSAGE_CONTENT_PREFIX = "content-"

# Guards against walking forever if the page is unexpectedly large.
MAX_SEARCH_NODES = 5000


def getHtmlId(obj, useCache=True):
	"""The HTML id of a web element, whether NVDA reaches it through IAccessible2 or UI Automation.
	Each lookup is a call into the Teams process, so the result is remembered on the object.
	Pass useCache=False to ask Teams again, which gives an empty id once the element has been removed."""
	cached = getattr(obj, "_teamsChatReaderHtmlId", None)
	if useCache and cached is not None:
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
	# The id is read afresh: the remembered one still matches after Teams has removed the pane.
	try:
		return pane.parent is not None and getHtmlId(pane, useCache=False) == MESSAGE_PANE_ID
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


def forgetCachedObjects():
	global _cachedPane, _cachedMessageContainer, _confirmedCompleteContainer
	_cachedPane = None
	_cachedMessageContainer = None
	_confirmedCompleteContainer = None


def getRecentMessages(count):
	"""Up to count message objects, most recent first."""
	usedCachedPane = _cachedPane is not None
	messages = searchRecentMessages(count)
	# Teams rebuilds the chat after a visit to another view such as Activity, and the old elements can still
	# look alive. If the remembered ones gave nothing, forget them and search again from scratch.
	if not messages and usedCachedPane:
		log.debug("Teams Chat Reader: no messages from remembered pane, searching again")
		forgetCachedObjects()
		messages = searchRecentMessages(count)
	return messages


def searchRecentMessages(count):
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


# Debug capture: writes what NVDA sees of Teams to the NVDA log, to work out how to find things such as
# calendar events. The capture includes chat and calendar text, so it should be checked before it is shared.

# A full capture can freeze NVDA for a few seconds; this keeps it bounded.
MAX_CAPTURE_NODES = 4000
MAX_CAPTURE_TEXT = 300


def describeForCapture(obj):
	"""One line about an element: what it is, what it says and the HTML details that help find it again."""
	parts = []

	def add(label, getValue):
		try:
			value = getValue()
		except Exception:
			return
		if value:
			text = str(value).replace("\n", " ")
			if len(text) > MAX_CAPTURE_TEXT:
				text = text[:MAX_CAPTURE_TEXT] + "..."
			parts.append("{}={!r}".format(label, text))

	add("role", lambda: obj.role.name.lower())
	add("name", lambda: obj.name)
	add("value", lambda: obj.value)
	add("description", lambda: obj.description)
	add("id", lambda: getHtmlId(obj))
	add("states", lambda: ",".join(sorted(state.name.lower() for state in obj.states)))
	add("attributes", lambda: ";".join(
		"{}:{}".format(key, value) for key, value in sorted(obj.IA2Attributes.items()) if key != "id"))
	return " ".join(parts) or "(unreadable element)"


def describeAncestorPath(obj):
	"""The roles and ids from the document down to obj's parent, for example document > region#chat > list."""
	path = []
	try:
		obj = obj.parent
		while obj and len(path) < 100:
			step = obj.role.name.lower()
			htmlId = getHtmlId(obj)
			if htmlId:
				step += "#" + htmlId
			path.append(step)
			if obj.role == controlTypes.Role.DOCUMENT:
				break
			obj = obj.parent
	except Exception:
		path.append("(unreadable)")
	return " > ".join(reversed(path))


def captureFocusAncestry(obj):
	lines = []
	while obj and len(lines) < 100:
		lines.append(describeForCapture(obj))
		try:
			obj = obj.parent
		except Exception:
			lines.append("(parent unreadable)")
			break
	return lines


def captureTree(root):
	"""Every element below root, indented by depth, in document order."""
	lines = []
	stack = [(root, 0)]
	while stack and len(lines) < MAX_CAPTURE_NODES:
		obj, depth = stack.pop()
		lines.append("  " * depth + describeForCapture(obj))
		kids = []
		try:
			child = obj.firstChild
			while child:
				kids.append(child)
				child = child.next
		except Exception:
			lines.append("  " * (depth + 1) + "(children unreadable)")
		stack.extend((kid, depth + 1) for kid in reversed(kids))
	if stack:
		lines.append("... stopped after {} elements".format(MAX_CAPTURE_NODES))
	return lines


def describeCachedObjects():
	if _cachedPane is None:
		pane = "none"
	else:
		pane = "alive" if isPaneAlive(_cachedPane) else "removed"
	return "Remembered message pane: {}, remembered message container: {}".format(
		pane, "none" if _cachedMessageContainer is None else "set")


# Builds on NVDA's own Teams support, which stops message menus from taking focus.
class AppModule(BuiltinTeamsAppModule):

	scriptCategory = "Teams Chat Reader"

	# The message the last press read, so a second press can copy it without searching again.
	_lastMessage = None
	# The key of the last press. NVDA counts any quick repeat of this script as a double press, even with a
	# different number key, so a copy only happens when the same key was pressed twice.
	_lastKey = None
	# Turned on by the debug command; every focus change in Teams is then written to the log.
	_logFocus = False

	def event_gainFocus(self, obj, nextHandler):
		if self._logFocus:
			try:
				log.info("Teams Chat Reader focus: {}\n  in {}".format(describeForCapture(obj), describeAncestorPath(obj)))
			except Exception:
				log.error("Teams Chat Reader: failed to log focus", exc_info=True)
		nextHandler()

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
		gestures=["kb:alt+{}".format(n) for n in "1234567890"],
	)
	def script_readRecentMessage(self, gesture):
		key = gesture.mainKeyName
		if getLastScriptRepeatCount() == 1 and key == self._lastKey:
			self._copyLastMessage()
			return
		self._lastKey = key
		self._readMessage(10 if key == "0" else int(key))

	@script(
		description=(
			"Teams Chat Reader debugging: write the focus and everything on the Teams page to the NVDA log. "
			"The capture includes chat and calendar text"
		),
		gesture="kb:NVDA+alt+shift+d",
	)
	def script_captureForDebugging(self, gesture):
		ui.message("Capturing")
		start = time.perf_counter()
		lines = ["Teams Chat Reader capture", describeCachedObjects(), "Focus and its ancestors, nearest first:"]
		focus = api.getFocusObject()
		lines.extend("  " + line for line in captureFocusAncestry(focus))
		doc = getTeamsDocument()
		if doc:
			lines.append("Page:")
			pageLines = captureTree(doc)
			lines.extend(pageLines)
		else:
			lines.append("No Teams page found")
			pageLines = []
		log.info("\n".join(lines))
		ui.message("Captured {} elements in {:.0f} seconds".format(len(pageLines), time.perf_counter() - start))

	@script(
		description=(
			"Teams Chat Reader debugging: turn on or off writing every focus change in Teams to the NVDA log. "
			"The log then includes the text of whatever you move to"
		),
		gesture="kb:NVDA+alt+shift+f",
	)
	def script_toggleFocusLogging(self, gesture):
		AppModule._logFocus = not AppModule._logFocus
		ui.message("Focus logging on" if AppModule._logFocus else "Focus logging off")
