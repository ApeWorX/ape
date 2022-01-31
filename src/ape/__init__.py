import signal
from sqlite3 import converters

signal.signal(signal.SIGINT, lambda s, f: _sys.exit(130))

import sys as _sys
from functools import partial

from .contracts import _Contract
from .managers import (
    Project,
    _account_manager,
    _chain_manager,
    _compiler_manager,
    _config_manager,
    _conversion_manager,
    _network_manager,
    _plugin_manager,
)
from .managers.project import _DependencyManager

# Wiring together the application

plugin_manager = _plugin_manager
"""Manages plugins for the current project. See :class:`ape.plugins.PluginManager`."""

config = _config_manager
"""The active configs for the current project. See :class:`ape.managers.config.ConfigManager`."""

# Main types we export for the user
compilers = _compiler_manager
"""Manages compilers for the current project. See
:class:`ape.managers.compilers.CompilerManager`."""

networks = _network_manager
"""Manages the networks for the current project. See
:class:`ape.managers.networks.NetworkManager`."""

chain = _chain_manager
"""
The current connected blockchain; requires an active provider.
Useful for development purposes, such as controlling the state of the blockchain.
Also handy for querying data about the chain and managing local caches.
"""

accounts = _account_manager
"""Manages accounts for the current project. See :class:`ape.managers.accounts.AccountManager`."""

project = Project(path=config.PROJECT_FOLDER)
"""The currently active project. See :class:`ape.managers.project.ProjectManager`."""

_DependencyManager.project_manager = project

Contract = partial(_Contract, networks=networks, converters=converters)
"""User-facing class for instantiating contracts. See :class:`ape.contracts.base._Contract`."""

convert = _conversion_manager.convert
"""Conversion utility function. See :class:`ape.managers.converters.ConversionManager`."""

__all__ = [
    "accounts",
    "chain",
    "config",
    "convert",
    "Contract",
    "networks",
    "project",
    "Project",  # So you can load other projects
]
