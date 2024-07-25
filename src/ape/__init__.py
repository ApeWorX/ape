import signal
import threading
import traceback
import os

if threading.current_thread() is threading.main_thread():
    # If we are in the main thread, we can safely set the signal handler
    signal.signal(signal.SIGINT, lambda s, f: _sys.exit(130))

import sys as _sys


_HOME_DIR = os.path.expanduser("~")


def custom_exception_hook(exctype, value, tb):
    # Format the traceback
    formatted_traceback = traceback.format_exception(exctype, value, tb)

    # Filter out the home directory from the traceback
    filtered_traceback = []
    for line in formatted_traceback:
        if _HOME_DIR in line:
            filtered_traceback.append(line.replace(_HOME_DIR, "$HOME"))
        else:
            filtered_traceback.append(line)

    # Print the filtered traceback
    for line in filtered_traceback:
        _sys.stderr.write(line)

# Set the custom exception hook
_sys.excepthook = custom_exception_hook

from ape.managers.project import ProjectManager as Project
from ape.pytest.contextmanagers import RevertsContextManager
from ape.utils import ManagerAccessMixin as _ManagerAccessMixin

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

project = _ManagerAccessMixin.local_project
"""The currently active project. See :class:`ape.managers.project.ProjectManager`."""

Contract = chain.contracts.instance_at
"""User-facing class for instantiating contracts."""

convert = _ManagerAccessMixin.conversion_manager.convert
"""Conversion utility function. See :class:`ape.managers.converters.ConversionManager`."""

reverts = RevertsContextManager
"""
Catch and expect contract logic reverts. Resembles ``pytest.raises()``.
"""


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
    "reverts",
]
