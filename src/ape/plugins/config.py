from typing import Type

from ape.api.config import PluginConfig

from .pluggy_patch import PluginType, hookspec


class Config(PluginType):
    @hookspec
    def config_class(self) -> Type[PluginConfig]:
        """
        Returns a :class:`ape.api.config.PluginConfig` parser class that can be
        used to deconstruct the user config options for this plugins.

        NOTE: If none are specified, all injected :class:`ape.api.config.PluginConfig`'s are empty.
        """
