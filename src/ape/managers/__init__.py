from pathlib import Path

from ape.utils import USER_AGENT, ManagerAccessMixin

from .accounts import AccountManager
from .chain import ChainManager
from .compilers import CompilerManager
from .config import ConfigManager
from .converters import ConversionManager
from .networks import NetworkManager
from .plugins import PluginManager
from .project import ProjectManager
from .query import QueryManager

ManagerAccessMixin.plugin_manager = PluginManager()
ManagerAccessMixin.config_manager = ConfigManager(
    request_header={"User-Agent": USER_AGENT},
)
ManagerAccessMixin.compiler_manager = CompilerManager()
ManagerAccessMixin.network_manager = NetworkManager()
ManagerAccessMixin.query_manager = QueryManager()
ManagerAccessMixin.conversion_manager = ConversionManager()
ManagerAccessMixin.chain_manager = ChainManager()
ManagerAccessMixin.account_manager = AccountManager()
ManagerAccessMixin.local_project = ProjectManager(Path.cwd())
ManagerAccessMixin.Project = ProjectManager
