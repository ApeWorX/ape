from typing import Type

from ape.api.config import ConfigItem

from .pluggy_patch import PluginType, hookspec


class Config(PluginType):
    @hookspec
    def config_class(self) -> Type[ConfigItem]:
        """
        Returns a ConfigItem parser class that can be used to deconstruct the user
        config options for this plugins.

        NOTE: If none are specified, all injected `ConfigItem`s are empty
        """
