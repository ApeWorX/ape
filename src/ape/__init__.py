import signal

signal.signal(signal.SIGINT, lambda s, f: _sys.exit(130))

import sys as _sys
from functools import partial as _partial
from pathlib import Path as _Path

from .contracts import _Contract
from .managers.accounts import AccountManager as _AccountManager
from .managers.chain import ChainManager as _ChainManager
from .managers.compilers import CompilerManager as _CompilerManager
from .managers.config import ConfigManager as _ConfigManager
from .managers.converters import ConversionManager as _ConversionManager
from .managers.networks import NetworkManager as _NetworkManager
from .managers.project import ProjectManager as Project
from .managers.project import _DependencyManager
from .plugins import PluginManager as _PluginManager
from .utils import USER_AGENT

# Wiring together the application
_data_folder = _Path.home().joinpath(".ape")

plugin_manager = _PluginManager()
"""Manages plugins for the current project. See :class:`ape.plugins.PluginManager`."""

_DependencyManager.plugin_manager = plugin_manager
_dependency_manager = _DependencyManager(data_folder=_data_folder)

_ConfigManager.plugin_manager = plugin_manager
_ConfigManager._dependency_manager = _dependency_manager
config = _ConfigManager(
    # Store all globally-cached files
    data_folder=_data_folder,
    # NOTE: For all HTTP requests we make
    request_header={
        "User-Agent": USER_AGENT,
    },
    # What we are considering to be the starting project directory
    project_folder=_Path.cwd(),
)
"""The active configs for the current project. See :class:`ape.managers.config.ConfigManager`."""

# Main types we export for the user

_CompilerManager.config = config
_CompilerManager.plugin_manager = plugin_manager
compilers = _CompilerManager()
"""Manages compilers for the current project. See
:class:`ape.managers.compilers.CompilerManager`."""

_NetworkManager.config = config
_NetworkManager.plugin_manager = plugin_manager
networks = _NetworkManager()
"""Manages the networks for the current project. See
:class:`ape.managers.networks.NetworkManager`."""

_ConversionManager.config = config
_ConversionManager.plugin_manager = plugin_manager
_ConversionManager.networks = networks
_converters = _ConversionManager()

_ChainManager._networks = networks
_ChainManager._converters = _converters
chain = _ChainManager()
"""
The current connected blockchain; requires an active provider.
Useful for development purposes, such as controlling the state of the blockchain.
Also handy for querying data about the chain and managing local caches.
"""

_AccountManager.config = config
_AccountManager.converters = _converters
_AccountManager.plugin_manager = plugin_manager
_AccountManager.network_manager = networks
accounts = _AccountManager()
"""Manages accounts for the current project. See :class:`ape.managers.accounts.AccountManager`."""

Project.config = config
Project.compilers = compilers
Project.networks = networks
Project.converter = _converters
Project.plugin_manager = plugin_manager
"""User-facing class for instantiating Projects (in addition to the currently
active ``project``). See :class:`ape.managers.project.ProjectManager`."""

project = Project(path=config.PROJECT_FOLDER)
"""The currently active project. See :class:`ape.managers.project.ProjectManager`."""

_DependencyManager.project_manager = project

Contract = _partial(_Contract, networks=networks, converters=_converters)
"""User-facing class for instantiating contracts. See :class:`ape.contracts.base._Contract`."""

convert = _converters.convert
"""Conversion utility function. See :class:`ape.managers.converters.ConversionManager`."""

__all__ = [
    "accounts",
    "chain",
    "compilers",
    "config",
    "convert",
    "Contract",
    "networks",
    "project",
    "Project",  # So you can load other projects
]
