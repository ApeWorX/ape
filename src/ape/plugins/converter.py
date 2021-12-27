from typing import Iterator, Tuple, Type

from ape.api import ConverterAPI

from .pluggy_patch import PluginType, hookspec


class ConversionPlugin(PluginType):
    """
    A plugin for converting values. The `ape-ens <https://github.com/ApeWorX/ape-ens>`__
    plugin is an example of a conversion-plugin.
    """

    @hookspec
    def converters(self) -> Iterator[Tuple[str, Type[ConverterAPI]]]:
        """
        A hook that returns an iterator of tuples of a string ABI type and a
        ``ConverterAPI`` subclass.

        Usage example::

            @plugins.register(plugins.ConversionPlugin)
            def converters():
                yield int, MweiConversions

        Returns:
            Iterator[tuple[str, Type[:class:`~ape.api.convert.ConverterAPI`]]]
        """
