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

config = _ConfigManager(
    # Store all globally-cached files
    data_folder=_Path.home().joinpath(".ape"),
    # NOTE: For all HTTP requests we make
    request_header={
        "User-Agent": USER_AGENT,
    },
    # What we are considering to be the starting project directory
    project_folder=_Path.cwd(),
    plugin_manager=plugin_manager,
)
"""The active configs for the current project. See :class:`ape.managers.config.ConfigManager`."""

# Main types we export for the user

compilers = _CompilerManager(config=config, plugin_manager=plugin_manager)
"""Manages compilers for the current project. See
:class:`ape.managers.compilers.CompilerManager`."""

networks = _NetworkManager(config=config, plugin_manager=plugin_manager)
"""Manages the networks for the current project. See
:class:`ape.managers.networks.NetworkManager`."""

_converters = _ConversionManager(config=config, plugin_manager=plugin_manager, networks=networks)

chain = _ChainManager(networks=networks, converters=_converters)
"""
The current connected blockchain; requires an active provider.
Useful for development purposes, such as controlling the state of the blockchain.
Also handy for querying data about the chain and managing local caches.
"""

accounts = _AccountManager(
    config=config, converters=_converters, plugin_manager=plugin_manager, network_manager=networks
)
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

project = Project(path=config.PROJECT_FOLDER)
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
