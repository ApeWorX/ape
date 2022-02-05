from pathlib import Path as _Path

from ape.plugins import PluginManager
from ape.utils import USER_AGENT, ManagerAccessBase

from .accounts import AccountManager
from .chain import ChainManager
from .compilers import CompilerManager
from .config import ConfigManager
from .converters import ConversionManager
from .networks import NetworkManager
from .project import ProjectManager as Project
from .project import _DependencyManager
from .query import QueryManager as _QueryManager

# Wiring together the application
_data_folder = _Path.home().joinpath(".ape")
_project_folder = _Path.cwd()

_plugin_manager = PluginManager()
ManagerAccessBase.plugin_manager = _plugin_manager

_dependency_manager = _DependencyManager(data_folder=_data_folder)
ManagerAccessBase.dependency_manager = _dependency_manager

_config_manager = ConfigManager(
    # Store all globally-cached files
    DATA_FOLDER=_data_folder,
    # NOTE: For all HTTP requests we make
    REQUEST_HEADER={
        "User-Agent": USER_AGENT,
    },
    # What we are considering to be the starting project directory
    PROJECT_FOLDER=_project_folder,
)
ManagerAccessBase.config_manager = _config_manager

_compiler_manager = CompilerManager()
ManagerAccessBase.compiler_manager = _compiler_manager

_network_manager = NetworkManager()
ManagerAccessBase.network_manager = _network_manager

_query_manager = _QueryManager()
ManagerAccessBase.query_manager = _query_manager

_conversion_manager = ConversionManager()
ManagerAccessBase.conversion_manager = _conversion_manager

_chain_manager = ChainManager()
ManagerAccessBase.chain_manager = _chain_manager

_account_manager = AccountManager()
ManagerAccessBase.account_manager = _account_manager

_project_manager = Project(path=_project_folder)
ManagerAccessBase.project_manager = _project_manager

__all__ = [
    "_account_manager",
    "_chain_manager",
    "_compiler_manager",
    "_config_manager",
    "_conversion_manager",
    "_network_manager",
    "_project_manager",
    "Project",
    "query",
]
