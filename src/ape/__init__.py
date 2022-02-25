import signal

signal.signal(signal.SIGINT, lambda s, f: _sys.exit(130))

import sys as _sys
from functools import partial as _partial

from ape.utils import ManagerAccessBase as _ManagerAccessBase

from .contracts import _Contract
from .managers.project import ProjectManager as Project

# Wiring together the application

plugin_manager = _ManagerAccessBase.plugin_manager
"""Manages plugins for the current project. See :class:`ape.plugins.PluginManager`."""

config = _ManagerAccessBase.config_manager
"""The active configs for the current project. See :class:`ape.managers.config.ConfigManager`.
# NOTE: config is an injected property.
"""

# Main types we export for the user
compilers = _ManagerAccessBase.compiler_manager
"""Manages compilers for the current project. See
:class:`ape.managers.compilers.CompilerManager`."""

networks = _ManagerAccessBase.network_manager
"""Manages the networks for the current project. See
:class:`ape.managers.networks.NetworkManager`."""

_converters = _ManagerAccessBase.conversion_manager

chain = _ManagerAccessBase.chain_manager
"""
The current connected blockchain; requires an active provider.
Useful for development purposes, such as controlling the state of the blockchain.
Also handy for querying data about the chain and managing local caches.
"""

accounts = _ManagerAccessBase.account_manager
"""Manages accounts for the current project. See :class:`ape.managers.accounts.AccountManager`."""

project = _ManagerAccessBase.project_manager
"""The currently active project. See :class:`ape.managers.project.ProjectManager`."""

Contract = _partial(_Contract, networks=networks, converters=_converters)
"""User-facing class for instantiating contracts. See :class:`ape.contracts.base._Contract`."""

convert = _ManagerAccessBase.conversion_manager.convert
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
