"""Package the add-on folder into dist/teamsChatReader.nvda-addon.

The file name has no version in it, so the README's "latest release" download link keeps working.
"""

import pathlib
import zipfile

ROOT = pathlib.Path(__file__).parent
SOURCE = ROOT / "addon"
OUTPUT = ROOT / "dist" / "teamsChatReader.nvda-addon"


def main():
	OUTPUT.parent.mkdir(exist_ok=True)
	with zipfile.ZipFile(OUTPUT, "w", zipfile.ZIP_DEFLATED) as bundle:
		for path in sorted(SOURCE.rglob("*")):
			if path.is_file() and "__pycache__" not in path.parts:
				bundle.write(path, path.relative_to(SOURCE).as_posix())
	print("Built", OUTPUT)


if __name__ == "__main__":
	main()
