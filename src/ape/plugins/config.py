from typing import Type

from ape.api import PluginConfig

from .pluggy_patch import PluginType, hookspec


class Config(PluginType):
    """
    A registered config item. Plugins register config implementations
    when they allow additional user-configuration, set in the ``ape-config.yaml``.
    See the :class:`~ape.managers.config.ConfigManager` documentation for more
    information on the ``ape-config.yaml``.
    """

    @hookspec
    def config_class(self) -> Type[PluginConfig]:
        """
        A hook that returns a :class:`~ape.api.config.PluginConfig` parser class that can be
        used to deconstruct the user config options for this plugins.

        **NOTE**: If none are specified, all injected :class:`ape.api.config.PluginConfig`'s
        are empty.

        Usage example::

            @plugins.register(plugins.Config)
            def config_class():
                return MyPluginConfig

        Returns:
            Type[:class:`~ape.api.config.PluginConfig`]
        """
