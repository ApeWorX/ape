import signal
import threading

if threading.current_thread() is threading.main_thread():
    # If we are in the main thread, we can safely set the signal handler
    signal.signal(signal.SIGINT, lambda s, f: _sys.exit(130))

import sys as _sys

__all__ = [
    "accounts",
    "chain",
    "compilers",
    "config",
    "convert",
    "Contract",
    "fixture",
    "networks",
    "project",
    "Project",  # So you can load other projects
    "reverts",
]


def __getattr__(name: str):
    if name not in __all__:
        raise AttributeError(name)

    elif name == "reverts":
        from ape.pytest.contextmanagers import RevertsContextManager

        return RevertsContextManager

    elif name == "fixture":
        from ape.pytest.fixtures import fixture

        return fixture

    else:
        from ape.utils.basemodel import ManagerAccessMixin as access

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
