import functools
<<<<<<< HEAD
import importlib
from importlib.metadata import distributions
from typing import Any, Callable, Generator, Iterator, List, Optional, Set, Tuple, Type
=======
from typing import Any, Callable, Type
>>>>>>> 797ed67c (move PluginManager to src/ape/managers/plugins.py and clean_plugin_name to ape/plugins/_utils to avoid circular import)

from ape.managers.plugins import PluginManager

from .account import AccountPlugin
from .compiler import CompilerPlugin
from .config import Config
from .converter import ConversionPlugin
from .network import EcosystemPlugin, ExplorerPlugin, NetworkPlugin, ProviderPlugin
from .pluggy_patch import PluginType, hookimpl
from .pluggy_patch import plugin_manager as pluggy_manager
from .project import DependencyPlugin, ProjectPlugin
from .query import QueryPlugin


class PluginError(Exception):
    pass


# Combine all the plugins together via subclassing (merges `hookspec`s)
class AllPluginHooks(
    Config,
    AccountPlugin,
    CompilerPlugin,
    ConversionPlugin,
    DependencyPlugin,
    EcosystemPlugin,
    ExplorerPlugin,
    NetworkPlugin,
    ProjectPlugin,
    ProviderPlugin,
    QueryPlugin,
):
    pass


# All hookspecs are registered
pluggy_manager.add_hookspecs(AllPluginHooks)


def get_hooks(plugin_type):
    return [name for name, method in plugin_type.__dict__.items() if hasattr(method, "ape_spec")]


def register(plugin_type: Type[PluginType], **hookimpl_kwargs) -> Callable:
    """
    Register your plugin to ape. You must call this decorator to get your plugins
    included in ape's plugin ecosystem.

    Usage example::

        @plugins.register(plugins.AccountPlugin)  # 'register()' example
        def account_types():
            return AccountContainer, KeyfileAccount

    Args:
        plugin_type (Type[:class:`~ape.plugins.pluggy_patch.PluginType`]): The plugin
          type to register.

        hookimpl_kwargs: Return-values required by the plugin type.

    Returns:
        Callable
    """

    # NOTE: we are basically checking that `plugin_type`
    #       is one of the parent classes of `Plugins`
    if not issubclass(AllPluginHooks, plugin_type):
        raise PluginError("Not a valid plugin type to register.")

    def check_hook(plugin_type, hookimpl_kwargs, fn):
        fn = hookimpl(fn, **hookimpl_kwargs)

        if not hasattr(plugin_type, fn.__name__):
            hooks = get_hooks(plugin_type)

            raise PluginError(
                f"Registered function `{fn.__name__}` is not"
                f" a valid hook for {plugin_type.__name__}, must be one of:"
                f" {hooks}."
            )

        return fn

    # NOTE: Get around issue with using `plugin_type` raw in `check_hook`
    return functools.partial(check_hook, plugin_type, hookimpl_kwargs)


def valid_impl(api_class: Any) -> bool:
    """
    Check if an API class is valid. The class must not have any unimplemented
    abstract methods.

    Args:
        api_class (any)

    Returns:
        bool
    """

    if isinstance(api_class, tuple):
        return all(valid_impl(c) for c in api_class)

    # Is not an ABC base class or abstractdataclass
    if not hasattr(api_class, "__abstractmethods__"):
        return True  # not an abstract class

    return len(api_class.__abstractmethods__) == 0


__all__ = [
    "PluginManager",
    "register",
]
