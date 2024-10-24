from collections.abc import Generator, Iterable, Iterator
from functools import cached_property
from importlib import import_module
from typing import Any, Optional

from ape.exceptions import ApeAttributeError
from ape.logging import logger
from ape.plugins._utils import CORE_PLUGINS, clean_plugin_name, get_plugin_dists
from ape.plugins.pluggy_patch import plugin_manager as pluggy_manager
from ape.utils.basemodel import _assert_not_ipython_check, only_raise_attribute_error
from ape.utils.misc import log_instead_of_fail


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


def _get_unimplemented_methods_warning(api, plugin_name: str) -> str:
    unimplemented_methods: list[str] = []

    # Find the best API name to warn about.
    if isinstance(api, (list, tuple)):
        if classes := [p for p in api if hasattr(p, "__name__")]:
            # Likely only ever a single class in a registration, but just in case.
            api_name = " - ".join([p.__name__ for p in classes if hasattr(p, "__name__")])
            for api_cls in classes:
                unimplemented_methods.extend(_get_unimplemented_methods(api_cls))

        else:
            # This would only happen if the registration consisted of all primitives.
            api_name = " - ".join(api)

    elif hasattr(api, "__name__"):
        api_name = api.__name__
        unimplemented_methods.extend(_get_unimplemented_methods(api))

    else:
        api_name = api

    message = f"'{api_name}' from '{plugin_name}' is not fully implemented."
    if unimplemented_methods:
        # NOTE: Sorted for consistency.
        methods_str = ", ".join(sorted(unimplemented_methods))
        message = f"{message} Remaining abstract methods: '{methods_str}'."

    return message


def _get_unimplemented_methods(api) -> Iterable[str]:
    if (abstract_methods := getattr(api, "__abstractmethods__", None)) and hasattr(
        abstract_methods, "__iter__"
    ):
        return api.__abstractmethods__

    return []


class PluginManager:
    _unimplemented_plugins: list[str] = []

    def __init__(self) -> None:
        self.__registered = False

    @log_instead_of_fail(default="<PluginManager>")
    def __repr__(self) -> str:
        return f"<{PluginManager.__name__}>"

    @only_raise_attribute_error
    def __getattr__(self, attr_name: str) -> Iterator[tuple[str, tuple]]:
        _assert_not_ipython_check(attr_name)

        # NOTE: The first time this method is called, the actual
        #  plugin registration occurs. Registration only happens once.
        self._register_plugins()

        if not hasattr(pluggy_manager.hook, attr_name):
            raise ApeAttributeError(f"{PluginManager.__name__} has no attribute '{attr_name}'.")

        # Do this to get access to the package name
        hook_fn = getattr(pluggy_manager.hook, attr_name)
        hookimpls = hook_fn.get_hookimpls()

        def get_plugin_name_and_hookfn(hook):
            return hook.plugin_name, getattr(hook.plugin, attr_name)()

        for plugin_name, results in map(get_plugin_name_and_hookfn, hookimpls):
            # NOTE: Some plugins return a tuple and some return iterators
            if not isinstance(results, Generator):
                validated_plugin = self._validate_plugin(plugin_name, results)
                if validated_plugin:
                    yield validated_plugin
            else:
                # Only if it's an iterator, provide results as a series
                for result in results:
                    validated_plugin = self._validate_plugin(plugin_name, result)
                    if validated_plugin:
                        yield validated_plugin

    @cached_property
    def registered_plugins(self) -> set[str]:
        plugins = list({n.replace("-", "_") for n in get_plugin_dists()})
        return {*plugins, *CORE_PLUGINS}

    def _register_plugins(self):
        if self.__registered:
            return

        plugins = list({n.replace("-", "_") for n in get_plugin_dists()})
        plugin_modules = tuple([*plugins, *CORE_PLUGINS])

        for module_name in plugin_modules:
            try:
                module = import_module(module_name)
                pluggy_manager.register(module)
            except Exception as err:
                if module_name in CORE_PLUGINS or module_name == "ape":
                    # Always raise core plugin registration errors.
                    raise

                logger.warn_from_exception(err, f"Error loading plugin package '{module_name}'.")

        self.__registered = True

    def _validate_plugin(self, plugin_name: str, plugin_cls) -> Optional[tuple[str, tuple]]:
        if valid_impl(plugin_cls):
            return clean_plugin_name(plugin_name), plugin_cls
        else:
            self._warn_not_fully_implemented_error(plugin_cls, plugin_name)
            return None

    def _warn_not_fully_implemented_error(self, results, plugin_name):
        if plugin_name in self._unimplemented_plugins:
            # Already warned
            return

        message = _get_unimplemented_methods_warning(results, plugin_name)
        logger.warning(message)

        # Record so we don't warn repeatedly
        self._unimplemented_plugins.append(plugin_name)
