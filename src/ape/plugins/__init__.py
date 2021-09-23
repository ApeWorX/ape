import functools
import importlib
import pkgutil
from typing import Any, Callable, Iterator, Tuple, Type, cast

from ape.logging import logger

from .account import AccountPlugin
from .compiler import CompilerPlugin
from .config import Config
from .converter import ConversionPlugin
from .network import EcosystemPlugin, ExplorerPlugin, NetworkPlugin, ProviderPlugin
from .pluggy_patch import PluginType, hookimpl, plugin_manager


class PluginError(Exception):
    pass


# Combine all the plugins together via subclassing (merges `hookspec`s)
class AllPluginHooks(
    Config,
    AccountPlugin,
    CompilerPlugin,
    ConversionPlugin,
    EcosystemPlugin,
    ExplorerPlugin,
    NetworkPlugin,
    ProviderPlugin,
):
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


def register(plugin_type: Type[PluginType], **hookimpl_kwargs) -> Callable:
    # NOTE: we are basically checking that `plugin_type`
    #       is one of the parent classes of `Plugins`
    if not issubclass(AllPluginHooks, plugin_type):
        raise PluginError("Not a valid plugin type to register")

    def check_hook(plugin_type, hookimpl_kwargs, fn):
        fn = hookimpl(fn, **hookimpl_kwargs)

        if not hasattr(plugin_type, fn.__name__):
            hooks = get_hooks(plugin_type)

            raise PluginError(
                f"Registered function `{fn.__name__}` is not"
                f" a valid hook for {plugin_type.__name__}, must be one of:"
                f" {hooks}"
            )

        return fn

    # NOTE: Get around issue with using `plugin_type` raw in `check_hook`
    return functools.partial(check_hook, plugin_type, hookimpl_kwargs)


def valid_impl(api_class: Any) -> bool:
    if isinstance(api_class, tuple):
        return all(valid_impl(c) for c in api_class)

    # Is not an ABC base class or abstractdataclass
    if not hasattr(api_class, "__abstractmethods__"):
        return True  # not an abstract class

    else:
        return len(api_class.__abstractmethods__) == 0


class PluginManager:
    def __init__(self):
        # NOTE: This actually loads the plugins, and should only be done once
        for _, name, ispkg in pkgutil.iter_modules():
            if name.startswith("ape_") and ispkg:
                try:
                    plugin_manager.register(importlib.import_module(name))
                except Exception:
                    logger.warning(f"Error loading plugin package '{name}'")

    def __getattr__(self, attr_name: str) -> Iterator[Tuple[str, tuple]]:
        if not hasattr(plugin_manager.hook, attr_name):
            raise AttributeError(f"{self.__class__.__name__} has no attribute '{attr_name}'")

        # Do this to get access to the package name
        hook_fn = getattr(plugin_manager.hook, attr_name)
        hookimpls = hook_fn.get_hookimpls()

        def get_plugin_name_and_hookfn(h):
            return h.plugin_name, getattr(h.plugin, attr_name)()

        for plugin_name, results in map(get_plugin_name_and_hookfn, hookimpls):
            # NOTE: Some plugins return a tuple and some return iterators
            if not isinstance(results, tuple) and hasattr(results, "__iter__"):
                # Only if it's an iterator, provider results as a series
                for result in results:
                    if valid_impl(result):
                        yield clean_plugin_name(plugin_name), result

                    else:
                        logger.warning(
                            f"'{result.__name__}' from '{plugin_name}' is not fully implemented"
                        )

            elif valid_impl(results):
                # Otherwise, provide results directly
                yield clean_plugin_name(plugin_name), results

            else:
                _warn_not_fully_implemented_error(results, plugin_name)


def _warn_not_fully_implemented_error(results, plugin_name):
    if isinstance(results, (tuple, list)):
        class_names = ", ".join((r.__name__ for r in results))
    else:
        class_names = results.__name__
    logger.warning(f"'{class_names}' from '{plugin_name}' is not fully implemented")


__all__ = [
    "PluginManager",
    "clean_plugin_name",
    "register",
]
