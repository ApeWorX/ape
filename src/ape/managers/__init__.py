from pathlib import Path as _Path

from ape.plugins import PluginManager
from ape.utils import USER_AGENT, ManagerAccessMixin

from .accounts import AccountManager
from .chain import ChainManager
from .compilers import CompilerManager
from .config import ConfigManager
from .converters import ConversionManager
from .networks import NetworkManager
from .project import DependencyManager, ProjectManager
from .query import QueryManager

# Wiring together the application
_data_folder = _Path.home().joinpath(".ape")
_project_folder = _Path.cwd()

ManagerAccessMixin.plugin_manager = PluginManager()

ManagerAccessMixin.dependency_manager = DependencyManager(data_folder=_data_folder)

ManagerAccessMixin.config_manager = ConfigManager(
    # Store all globally-cached files
    DATA_FOLDER=_data_folder,
    # NOTE: For all HTTP requests we make
    REQUEST_HEADER={
        "User-Agent": USER_AGENT,
    },
    # What we are considering to be the starting project directory
    PROJECT_FOLDER=_project_folder,
)

ManagerAccessMixin.compiler_manager = CompilerManager()

ManagerAccessMixin.network_manager = NetworkManager()

ManagerAccessMixin.query_manager = QueryManager()

ManagerAccessMixin.conversion_manager = ConversionManager()

ManagerAccessMixin.chain_manager = ChainManager()

ManagerAccessMixin.account_manager = AccountManager()

ManagerAccessMixin.project_manager = ProjectManager(path=_project_folder)
