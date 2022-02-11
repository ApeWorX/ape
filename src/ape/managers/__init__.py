from pathlib import Path as _Path

from ape.plugins import PluginManager
from ape.utils import USER_AGENT, ManagerAccessBase

from .accounts import AccountManager
from .chain import ChainManager
from .compilers import CompilerManager
from .config import ConfigManager
from .converters import ConversionManager
from .networks import NetworkManager
from .project import ProjectManager, _DependencyManager
from .query import QueryManager

# Wiring together the application
_data_folder = _Path.home().joinpath(".ape")
_project_folder = _Path.cwd()

ManagerAccessBase.plugin_manager = PluginManager()

ManagerAccessBase.dependency_manager = _DependencyManager(data_folder=_data_folder)

ManagerAccessBase.config_manager = ConfigManager(
    # Store all globally-cached files
    DATA_FOLDER=_data_folder,
    # NOTE: For all HTTP requests we make
    REQUEST_HEADER={
        "User-Agent": USER_AGENT,
    },
    # What we are considering to be the starting project directory
    PROJECT_FOLDER=_project_folder,
)

ManagerAccessBase.compiler_manager = CompilerManager()

ManagerAccessBase.network_manager = NetworkManager()

ManagerAccessBase.query_manager = QueryManager()

ManagerAccessBase.conversion_manager = ConversionManager()

ManagerAccessBase.chain_manager = ChainManager()

ManagerAccessBase.account_manager = AccountManager()

ManagerAccessBase.project_manager = ProjectManager(path=_project_folder)

ManagerAccessBase.Project = ProjectManager
