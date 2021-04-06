import functools
import importlib
import pkgutil
from typing import cast

from .account import AccountPlugin
from .config import Config
from .pluggy_patch import hookimpl, plugin_manager


class PluginError(Exception):
    pass


# Combine all the plugins together via subclassing (merges `hookspec`s)
class AllPluginHooks(AccountPlugin, Config):
    pass


# All hookspecs are registered
plugin_manager.add_hookspecs(AllPluginHooks)

# Add cast so that mypy knows that pm.hook is actually a `Plugins` instance.
# Without this hint there really is no way for mypy to know this.
plugin_manager.hook = cast(AllPluginHooks, plugin_manager.hook)


def clean_plugin_name(name: str) -> str:
    return name.replace("ape_", "").replace("_", "-")


def get_hooks(plugin_type):
    return [name for name, method in plugin_type.__dict__.items() if hasattr(method, "ape_spec")]


def register(plugin_type):
    # NOTE: we are basically checking that `plugin_type`
    #       is one of the parent classes of `Plugins`
    if not issubclass(AllPluginHooks, plugin_type):
        raise PluginError("Not a valid plugin type to register")

    def check_hook(plugin_type, fn):
        fn = hookimpl(fn)

        if not hasattr(plugin_type, fn.__name__):
            hooks = get_hooks(plugin_type)

            raise PluginError(
                f"Registered function `{fn.__name__}` is not"
                f" a valid hook for {plugin_type.__name__}, must be one of:"
                f" {hooks}"
            )

        return fn

    # NOTE: Get around issue with using `plugin_type` raw in `check_hook`
    return functools.partial(check_hook, plugin_type)


# NOTE: This actually loads the plugins, and should only be used once
for _, name, ispkg in pkgutil.iter_modules():
    if name.startswith("ape_") and ispkg:
        plugin_manager.register(importlib.import_module(name))


__all__ = [
    "plugin_manager",
    "clean_plugin_name",
    "register",
]
