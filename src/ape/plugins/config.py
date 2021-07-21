from typing import Type

from ape.api.config import ConfigItem

from .pluggy_patch import PluginType, hookspec


class Config(PluginType):
    @hookspec
    def config_class(self) -> Type[ConfigItem]:
        """
        Returns a :class:`ape.api.config.ConfigItem` parser class that can be
        used to deconstruct the user config options for this plugins.

        NOTE: If none are specified, all injected :class:`ape.api.config.ConfigItem`'s are empty.
        """
