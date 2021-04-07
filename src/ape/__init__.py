import sys as _sys
from pathlib import Path as _Path

from .managers.accounts import AccountManager as _AccountManager
from .plugins import plugin_manager
from .project import Project

try:
    from importlib.metadata import PackageNotFoundError as _PackageNotFoundError  # type: ignore
    from importlib.metadata import version as _version  # type: ignore
except ModuleNotFoundError:
    from importlib_metadata import PackageNotFoundError as _PackageNotFoundError  # type: ignore
    from importlib_metadata import version as _version  # type: ignore

try:
    __version__ = _version(__name__)
except _PackageNotFoundError:
    # package is not installed
    __version__ = "<unknown>"

# Path constants for Ape
# NOTE: Make sure this exists for plugins to use
# NOTE: We overwrite this for testing
DATA_FOLDER = _Path.home().joinpath(".ape")


# For all HTTP requests we make
# NOTE: DO NOT OVERWRITE
_python_version = (
    f"{_sys.version_info.major}.{_sys.version_info.minor}"
    f".{_sys.version_info.micro} {_sys.version_info.releaselevel}"
)
REQUEST_HEADER = {
    "User-Agent": f"Ape/{__version__} (Python/{_python_version})",
}

# Wiring together the application
accounts = _AccountManager(plugin_manager)  # type: ignore
project = Project()


__all__ = [
    "accounts",
    "project",
    "Project",  # So you can load other projects
]
