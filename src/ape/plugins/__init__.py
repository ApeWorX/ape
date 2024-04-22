import functools
import importlib
from importlib.metadata import distributions
from typing import Any, Callable, Generator, Iterator, List, Optional, Set, Tuple, Type

from ape.exceptions import ApeAttributeError
from ape.logging import logger
from ape.plugins._utils import CORE_PLUGINS, clean_plugin_name
from ape.utils.basemodel import _assert_not_ipython_check
from ape.utils.misc import log_instead_of_fail

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


class PluginManager:
    _unimplemented_plugins: List[str] = []

    def __init__(self) -> None:
        self.__registered = False

    @log_instead_of_fail(default="<PluginManager>")
    def __repr__(self) -> str:
        return f"<{PluginManager.__name__}>"

    def __getattr__(self, attr_name: str) -> Iterator[Tuple[str, Tuple]]:
        _assert_not_ipython_check(attr_name)

        # NOTE: The first time this method is called, the actual
        #  plugin registration occurs. Registration only happens once.
        self._register_plugins()

        if not hasattr(pluggy_manager.hook, attr_name):
            raise ApeAttributeError(f"{PluginManager.__name__} has no attribute '{attr_name}'.")

        # Do this to get access to the package name
        hook_fn = getattr(pluggy_manager.hook, attr_name)
        hookimpls = hook_fn.get_hookimpls()

        def get_plugin_name_and_hookfn(h):
            return h.plugin_name, getattr(h.plugin, attr_name)()

        for plugin_name, results in map(get_plugin_name_and_hookfn, hookimpls):
            # NOTE: Some plugins return a tuple and some return iterators
            if not isinstance(results, Generator):
                validated_plugin = self._validate_plugin(plugin_name, results)
                if validated_plugin:
                    yield validated_plugin
            else:
                # Only if it's an iterator, provider results as a series
                for result in results:
                    validated_plugin = self._validate_plugin(plugin_name, result)
                    if validated_plugin:
                        yield validated_plugin

    @property
    def registered_plugins(self) -> Set[str]:
        self._register_plugins()
        return {x[0] for x in pluggy_manager.list_name_plugin()}

    def _register_plugins(self):
        if self.__registered:
            return

        plugins: list[str] = []
        for dist in distributions():
            if not (name := getattr(dist, "name", "")):
                continue
            elif name.startswith("ape-"):
                plugins.append(name.replace("-", "_"))

        plugin_modules = tuple([*plugins, *CORE_PLUGINS])

        for module_name in plugin_modules:
            try:
                module = importlib.import_module(module_name)
                pluggy_manager.register(module)
            except Exception as err:
                if module_name in CORE_PLUGINS:
                    # Always raise core plugin registration errors.
                    raise

                logger.warn_from_exception(err, f"Error loading plugin package '{module_name}'.")

        self.__registered = True

    def _validate_plugin(self, plugin_name: str, plugin_cls) -> Optional[Tuple[str, Tuple]]:
        if valid_impl(plugin_cls):
            return clean_plugin_name(plugin_name), plugin_cls
        else:
            self._warn_not_fully_implemented_error(plugin_cls, plugin_name)
            return None

    def _warn_not_fully_implemented_error(self, results, plugin_name):
        if plugin_name in self._unimplemented_plugins:
            # Already warned
            return

        unimplemented_methods = []

        # Find the best API name to warn about.
        if isinstance(results, (list, tuple)):
            classes = [p for p in results if hasattr(p, "__name__")]
            if classes:
                # Likely only ever a single class in a registration, but just in case.
                api_name = " - ".join([p.__name__ for p in classes if hasattr(p, "__name__")])
                for api_cls in classes:
                    if (
                        abstract_methods := getattr(api_cls, "__abstractmethods__", None)
                    ) and isinstance(abstract_methods, dict):
                        unimplemented_methods.extend(api_cls.__abstractmethods__)

            else:
                # This would only happen if the registration consisted of all primitives.
                api_name = " - ".join(results)

        elif hasattr(results, "__name__"):
            api_name = results.__name__
            if (abstract_methods := getattr(results, "__abstractmethods__", None)) and isinstance(
                abstract_methods, dict
            ):
                unimplemented_methods.extend(results.__abstractmethods__)

        else:
            api_name = results

        message = f"'{api_name}' from '{plugin_name}' is not fully implemented."
        if unimplemented_methods:
            methods_str = ", ".join(unimplemented_methods)
            message = f"{message} Remaining abstract methods: '{methods_str}'."

        logger.warning(message)

        # Record so we don't warn repeatedly
        self._unimplemented_plugins.append(plugin_name)


__all__ = [
    "PluginManager",
    "clean_plugin_name",
    "register",
]
