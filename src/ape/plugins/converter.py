from collections.abc import Iterator
from typing import TYPE_CHECKING

from .pluggy_patch import PluginType, hookspec

if TYPE_CHECKING:
    from ape.api.convert import ConverterAPI


class ConversionPlugin(PluginType):
    """
    A plugin for converting values. The `ape-ens <https://github.com/ApeWorX/ape-ens>`__
    plugin is an example of a conversion-plugin.
    """

    @hookspec
    def converters(self) -> Iterator[tuple[str, type["ConverterAPI"]]]:  # type: ignore[empty-body]
        """
        A hook that returns an iterator of tuples of a string ABI type and a
        ``ConverterAPI`` subclass.

        Usage example::

            @plugins.register(plugins.ConversionPlugin)
            def converters():
                yield int, MweiConversions

        Returns:
            Iterator[tuple[str, type[:class:`~ape.api.convert.ConverterAPI`]]]
        """
