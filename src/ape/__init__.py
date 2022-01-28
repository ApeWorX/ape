import signal

signal.signal(signal.SIGINT, lambda s, f: _sys.exit(130))

import sys as _sys
from functools import partial as _partial

from .contracts import _Contract
from .managers import Project, accounts, chain, config, converters, networks
from .managers.project import _DependencyManager

project = Project(path=config.PROJECT_FOLDER)
"""The currently active project. See :class:`ape.managers.project.ProjectManager`."""

_DependencyManager.project_manager = project

Contract = _partial(_Contract, networks=networks, converters=converters)
"""User-facing class for instantiating contracts. See :class:`ape.contracts.base._Contract`."""

convert = converters.convert
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
