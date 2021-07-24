from typing import Iterator, Tuple, Type

from ape.api import ConverterAPI

from .pluggy_patch import PluginType, hookspec


class ConversionPlugin(PluginType):
    @hookspec
    def converters(self) -> Iterator[Tuple[str, Type[ConverterAPI]]]:
        """
        Must return an iterator of tuples of a string ABIType and an ConverterAPI subclass
        """
