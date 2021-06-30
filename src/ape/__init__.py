import sys as _sys
from functools import partial as _partial
from pathlib import Path as _Path

from .api.contracts import _Contract
from .managers.accounts import AccountManager as _AccountManager
from .managers.compilers import CompilerManager as _CompilerManager
from .managers.config import ConfigManager as _ConfigManager
from .managers.networks import NetworkManager as _NetworkManager
from .managers.project import ProjectManager as _ProjectManager
from .plugins import PluginManager as _PluginManager
from .utils import get_package_version

__version__ = get_package_version(__name__)


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
compilers = _CompilerManager(config, plugin_manager)  # type: ignore
networks = _NetworkManager(config, plugin_manager)  # type: ignore
accounts = _AccountManager(config, plugin_manager, networks)  # type: ignore

Project = _partial(_ProjectManager, config=config, compilers=compilers)
project = Project(config.PROJECT_FOLDER)

Contract = _partial(_Contract, networks=networks)


__all__ = [
    "accounts",
    "compilers",
    "config",
    "Contract",
    "networks",
    "project",
    "Project",  # So you can load other projects
]
