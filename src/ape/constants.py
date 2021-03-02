from pathlib import Path as _Path

# Path constants for Ape
INSTALL_FOLDER = _Path(__file__).parent
DATA_FOLDER = _Path.home().joinpath(".ape")
DATA_SUBFOLDERS = ("accounts",)
PROJECT_FOLDER = _Path.cwd()
