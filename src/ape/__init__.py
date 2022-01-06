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
from .managers.project import ProjectManager as _ProjectManager
from .plugins import PluginManager as _PluginManager
from .utils import USER_AGENT

# Wiring together the application

plugin_manager = _PluginManager()
"""Manages plugins for the current project. See :class:`ape.plugins.PluginManager`."""

config = _ConfigManager(  # type: ignore
    # Store all globally-cached files
    DATA_FOLDER=_Path.home().joinpath(".ape"),
    # NOTE: For all HTTP requests we make
    REQUEST_HEADER={
        "User-Agent": USER_AGENT,
    },
    # What we are considering to be the starting project directory
    PROJECT_FOLDER=_Path.cwd(),
    plugin_manager=plugin_manager,
)
"""The active configs for the current project. See :class:`ape.managers.config.ConfigManager`."""

# Main types we export for the user

compilers = _CompilerManager(config, plugin_manager)  # type: ignore
"""Manages compilers for the current project. See
:class:`ape.managers.compilers.CompilerManager`."""

networks = _NetworkManager(config, plugin_manager)  # type: ignore
"""Manages the networks for the current project. See
:class:`ape.managers.networks.NetworkManager`."""

_converters = _ConversionManager(config, plugin_manager, networks)  # type: ignore

chain = _ChainManager(networks)  # type: ignore
"""
The current connected blockchain; requires an active provider.
Useful for development purposes, such as controlling the state of the blockchain.
Also handy for querying data about the chain and managing local caches.
"""

accounts = _AccountManager(config, _converters, plugin_manager, networks)  # type: ignore
"""Manages accounts for the current project. See :class:`ape.managers.accounts.AccountManager`."""

Project = _partial(
    _ProjectManager,
    config=config,
    compilers=compilers,
    networks=networks,
    converter=_converters,
)
"""User-facing class for instantiating Projects (in addition to the currently
active ``project``). See :class:`ape.managers.project.ProjectManager`."""

project = Project(config.PROJECT_FOLDER)
"""The currently active project. See :class:`ape.managers.project.ProjectManager`."""

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
