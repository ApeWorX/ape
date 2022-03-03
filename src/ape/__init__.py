import signal

signal.signal(signal.SIGINT, lambda s, f: _sys.exit(130))

import sys as _sys
from functools import partial as _partial

from ape.utils import ManagerAccessMixin as _ManagerAccessMixin

from .contracts import _Contract
from .managers.project import ProjectManager as Project

# Wiring together the application

config = _ManagerAccessMixin.config_manager
"""
The active configs for the current project. See :class:`ape.managers.config.ConfigManager`.
"""

# Main types we export for the user
compilers = _ManagerAccessMixin.compiler_manager
"""Manages compilers for the current project. See
:class:`ape.managers.compilers.CompilerManager`."""

networks = _ManagerAccessMixin.network_manager
"""Manages the networks for the current project. See
:class:`ape.managers.networks.NetworkManager`."""

chain = _ManagerAccessMixin.chain_manager
"""
The current connected blockchain; requires an active provider.
Useful for development purposes, such as controlling the state of the blockchain.
Also handy for querying data about the chain and managing local caches.
"""

accounts = _ManagerAccessMixin.account_manager
"""Manages accounts for the current project. See :class:`ape.managers.accounts.AccountManager`."""

project = _ManagerAccessMixin.project_manager
"""The currently active project. See :class:`ape.managers.project.ProjectManager`."""

Contract = _partial(
    _Contract, networks=networks, conversion_manager=_ManagerAccessMixin.conversion_manager
)
"""User-facing class for instantiating contracts. See :class:`ape.contracts.base._Contract`."""

convert = _ManagerAccessMixin.conversion_manager.convert
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
