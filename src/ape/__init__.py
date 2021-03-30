import sys as _sys
from pathlib import Path as _Path

from .api import Accounts as _Accounts
from .plugins import __load_plugins
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

# Exported Ape data types (Must not create circular dependencies with plugins)
accounts = _Accounts()

# NOTE: This is how plugins actually are brought into the namespace to be registered.
#       It also provides a convienent debugging endpoint. Should not be used directly.
# NOTE: Must be after exported data types to avoid circular reference issues
__discovered_plugins = __load_plugins()

# NOTE: Project must be last to load (loads project in current directory)
project = Project()


__all__ = [
    "accounts",
    "project",
    "Project",  # So you can load other projects
]
