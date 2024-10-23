import signal
import threading
from typing import Any

if threading.current_thread() is threading.main_thread():
    # If we are in the main thread, we can safely set the signal handler
    signal.signal(signal.SIGINT, lambda s, f: _sys.exit(130))

import sys as _sys
from importlib import import_module

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


def __getattr__(name: str) -> Any:
    if name not in __all__:
        raise AttributeError(name)

    elif name == "reverts":
        contextmanagers = import_module("ape.pytest.contextmanagers")
        return contextmanagers.RevertsContextManager

    else:
        access = import_module("ape.managers.project").ManagerAccessMixin
        if name == "Contract":
            return access.chain_manager.contracts.instance_at

        elif name == "Project":
            return access.Project

        elif name == "convert":
            return access.conversion_manager.convert

        # The rest are managers; we can derive the name.
        key = name
        if name == "project":
            key = "local_project"
        elif name.endswith("s"):
            key = f"{name[:-1]}_manager"
        else:
            key = f"{key}_manager"

        return getattr(access, key)
