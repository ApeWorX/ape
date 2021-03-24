import importlib
import pkgutil
from abc import ABCMeta
from typing import Callable, Dict, Generic, List, Type, TypeVar

import click
from dataclassy.dataclass import DataClassMeta

from .api.accounts import AccountContainerAPI
from .api.config import ConfigItem

_Provides = TypeVar("_Provides")
_PluginHookFn = Callable[[], _Provides]


class BasePlugin(Generic[_Provides]):
    provides: Type[_Provides]

    def __init__(self, name: str, hook_fn: _PluginHookFn):
        self.name = name
        self._hook_fn = hook_fn
        self._data = None

    @property
    def data(self):
        # Cache hook function return data
        if not self._data:
            data = self._hook_fn()

            # NOTE: Dynamic registration type check
            # (assures all values in `registered_plugins` are consistent)
            if isinstance(self.provides, (ABCMeta, DataClassMeta)):  # One of our `*API` classes
                if not issubclass(data, self.provides):
                    raise ValueError(
                        f"Registering a `{self.__class__.__name__}` must be a function "
                        f"that returns `{self.provides}`, not `{type(data).__name__}`"
                    )
            else:
                if not isinstance(data, self.provides):  # An external type
                    raise ValueError(
                        f"Registering a `{self.__class__.__name__}` must be a function "
                        f"that returns `{self.provides}`, not `{type(data).__name__}`"
                    )

            self._data = data

        return self._data


class Config(BasePlugin):
    provides = ConfigItem


class CliPlugin(BasePlugin):
    provides = click.Command


class AccountPlugin(BasePlugin):
    provides = AccountContainerAPI


# NOTE: These are the plugins that actually perform proper registration.
registered_plugins: Dict[Type[BasePlugin], List] = {
    Config: [],
    CliPlugin: [],
    AccountPlugin: [],
}

_PluginDecorator = Callable[[_PluginHookFn], _Provides]


# TODO: Make it so this function properly type-checks uses in plugins
def register(plugin_type: Type[BasePlugin]) -> _PluginDecorator:
    def add_plugin(hook_fn: _PluginHookFn) -> None:
        name = _clean_plugin_name(hook_fn.__module__)
        plugin = plugin_type(name, hook_fn)
        registered_plugins[plugin_type].append(plugin)

    return add_plugin


def _clean_plugin_name(name: str) -> str:
    return name.replace("ape_", "").replace("_", "-")


def __load_plugins():
    return {
        _clean_plugin_name(name): importlib.import_module(name)
        for _, name, ispkg in pkgutil.iter_modules()
        if name.startswith("ape_") and ispkg
    }
