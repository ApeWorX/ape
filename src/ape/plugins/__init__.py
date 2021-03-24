import importlib
import pkgutil
from typing import cast

from .account import AccountPlugin
from .cli import CliPlugin
from .config import Config
from .pluggy import hookimpl, plugin_manager


# Combine all the plugins together
class Plugins(AccountPlugin, CliPlugin, Config):
    pass


plugin_manager.add_hookspecs(Plugins)

# Add cast so that mypy knows that pm.hook is actually a MySpec instance.
# Without this hint there really is no way for mypy to know this.
plugin_manager.hook = cast(Plugins, plugin_manager.hook)


def clean_plugin_name(name: str) -> str:
    return name.replace("ape_", "").replace("_", "-")


def register(plugin_type):
    if not issubclass(Plugins, plugin_type):
        raise  # Not a valid plugin type to register

    def inner(fn):
        # TODO: Figure out how to rectify `fn` w/ `plugin_type`
        return hookimpl(fn)

    return inner


def __load_plugins():
    for _, name, ispkg in pkgutil.iter_modules():
        if name.startswith("ape_") and ispkg:
            plugin_manager.register(importlib.import_module(name))

    plugin_manager.load_setuptools_entrypoints("ape")

    return plugin_manager.get_plugins()
