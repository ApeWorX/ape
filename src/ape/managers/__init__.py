from pathlib import Path as _Path

from ape.plugins import PluginManager as _PluginManager
from ape.utils import USER_AGENT, ManagerAccessBase

from .accounts import AccountManager as _AccountManager
from .chain import ChainManager as _ChainManager
from .compilers import CompilerManager as _CompilerManager
from .config import ConfigManager as _ConfigManager
from .converters import ConversionManager as _ConversionManager
from .networks import NetworkManager as _NetworkManager
from .project import ProjectManager as Project
from .query import QueryManager as _QueryManager

# Wiring together the application

plugin_manager = _PluginManager()
"""Manages plugins for the current project. See :class:`ape.plugins.PluginManager`."""
ManagerAccessBase.plugin_manager = plugin_manager

config = _ConfigManager(
    # Store all globally-cached files
    data_folder=_Path.home().joinpath(".ape"),
    # NOTE: For all HTTP requests we make
    request_header={
        "User-Agent": USER_AGENT,
    },
    # What we are considering to be the starting project directory
    project_folder=_Path.cwd(),
)
"""The active configs for the current project. See :class:`ape.managers.config.ConfigManager`."""
ManagerAccessBase.config_manager = config

# Main types we export for the user
compilers = _CompilerManager()
"""Manages compilers for the current project. See
:class:`ape.managers.compilers.CompilerManager`."""
ManagerAccessBase.compiler_manager = compilers

networks = _NetworkManager()
"""Manages the networks for the current project. See
:class:`ape.managers.networks.NetworkManager`."""
ManagerAccessBase.network_manager = networks

query = _QueryManager()
"""Manages query actions for the current project. See
:class:`ape.managers.query.QueryManager`."""
ManagerAccessBase.query_manager = query

converters = _ConversionManager()
ManagerAccessBase.conversion_manager = converters

chain = _ChainManager()
"""
The current connected blockchain; requires an active provider.
Useful for development purposes, such as controlling the state of the blockchain.
Also handy for querying data about the chain and managing local caches.
"""
ManagerAccessBase.chain_manager = chain

accounts = _AccountManager()
"""Manages accounts for the current project. See :class:`ape.managers.accounts.AccountManager`."""
ManagerAccessBase.account_manager = accounts


__all__ = [
    "accounts",
    "chain",
    "config",
    "converters",
    "networks",
    "Project",
    "query",
]
