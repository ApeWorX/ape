import sys as _sys
from pathlib import Path as _Path

from .managers.accounts import AccountManager as _AccountManager
from .managers.compilers import CompilerManager as _CompilerManager
from .managers.config import ConfigManager as _ConfigManager
from .managers.project import ProjectManager as _ProjectManager
from .plugins import PluginManager as _PluginManager

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


# NOTE: DO NOT OVERWRITE
_python_version = (
    f"{_sys.version_info.major}.{_sys.version_info.minor}"
    f".{_sys.version_info.micro} {_sys.version_info.releaselevel}"
)

# Wiring together the application
plugin_manager = _PluginManager()
config = _ConfigManager(  # type: ignore
    # Store all globally-cached files
    DATA_FOLDER=_Path.home().joinpath(".ape"),
    # NOTE: For all HTTP requests we make
    REQUEST_HEADER={
        "User-Agent": f"Ape/{__version__} (Python/{_python_version})",
    },
    # What we are considering to be the starting project directory
    PROJECT_FOLDER=_Path.cwd(),
    plugin_manager=plugin_manager,
)

# Main types we export for the user
accounts = _AccountManager(config, plugin_manager)  # type: ignore
compilers = _CompilerManager(config, plugin_manager)  # type: ignore


def Project(path):
    return _ProjectManager(path=path, config=config, compilers=compilers)


project = Project(config.PROJECT_FOLDER)


__all__ = [
    "accounts",
    "compilers",
    "config",
    "project",
    "Project",  # So you can load other projects
]
