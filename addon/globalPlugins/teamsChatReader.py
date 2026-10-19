# Teams Chat Reader
# The reading commands live in appModules/teams.py. NVDA finds that module for classic Teams (teams.exe) by
# name, but new Teams runs as ms-teams.exe, which can't be a Python module name, so it is registered here.

import appModuleHandler
import globalPluginHandler

NEW_TEAMS_EXECUTABLE = "ms-teams"


class GlobalPlugin(globalPluginHandler.GlobalPlugin):

	def __init__(self):
		super().__init__()
		appModuleHandler.registerExecutableWithAppModule(NEW_TEAMS_EXECUTABLE, "teams")

	def terminate(self):
		appModuleHandler.unregisterExecutable(NEW_TEAMS_EXECUTABLE)
		super().terminate()
