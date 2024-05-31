import functools
from collections.abc import Callable

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


def register(plugin_type: type[PluginType], **hookimpl_kwargs) -> Callable:
    """
    Register your plugin to ape. You must call this decorator to get your plugins
    included in ape's plugin ecosystem.

    Usage example::

        @plugins.register(plugins.AccountPlugin)  # 'register()' example
        def account_types():
            return AccountContainer, KeyfileAccount

    Args:
        plugin_type (type[:class:`~ape.plugins.pluggy_patch.PluginType`]): The plugin
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


__all__ = [
    "register",
]
