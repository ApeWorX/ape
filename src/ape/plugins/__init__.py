import functools
import importlib
import pkgutil
from typing import cast

from .account import AccountPlugin
from .config import Config
from .pluggy import hookimpl, plugin_manager


class PluginError(Exception):
    pass


# Combine all the plugins together via subclassing (merges `hookspec`s)
class Plugins(AccountPlugin, Config):
    pass


# All hookspecs are registered
plugin_manager.add_hookspecs(Plugins)

# Add cast so that mypy knows that pm.hook is actually a `Plugins` instance.
# Without this hint there really is no way for mypy to know this.
plugin_manager.hook = cast(Plugins, plugin_manager.hook)


def clean_plugin_name(name: str) -> str:
    return name.replace("ape_", "").replace("_", "-")


def register(plugin_type):
    # NOTE: we are basically checking that `plugin_type`
    #       is one of the parent classes of `Plugins`
    if not issubclass(Plugins, plugin_type):
        raise PluginError("Not a valid plugin type to register")

    def check_hook(plugin_type, fn):
        fn = hookimpl(fn)

        if not hasattr(plugin_type, fn.__name__):
            hooks = [
                name for name, method in plugin_type.__dict__.items() if hasattr(method, "ape_spec")
            ]
            raise PluginError(
                f"Registered function `{fn.__name__}` is not"
                f" a valid hook for {plugin_type.__name__}, must be one of:"
                f" {hooks}"
            )

        return fn

    # NOTE: Get around issue with using `plugin_type` raw in `check_hook`
    return functools.partial(check_hook, plugin_type)


def __load_plugins():
    for _, name, ispkg in pkgutil.iter_modules():
        if name.startswith("ape_") and ispkg:
            plugin_manager.register(importlib.import_module(name))

    return plugin_manager.get_plugins()
