from typing import Any, Dict, List, Type

from dataclassy import dataclass
from eth_typing import ChecksumAddress
from eth_utils import is_checksum_address, is_hex
from hexbytes import HexBytes

from ape.api import ConverterAPI
from ape.plugins import PluginManager
from ape.utils import cached_property

from .config import ConfigManager
from .networks import NetworkManager


# NOTE: This utility converter ensures that all bytes args can accept hex too
class HexConverter(ConverterAPI):
    def is_convertible(self, value: str) -> bool:
        return is_hex(value)

    def convert(self, value: str) -> bytes:
        return HexBytes(value)


hex_converter = HexConverter(None, None)  # type: ignore


@dataclass
class ConversionManager:
    config: ConfigManager
    plugin_manager: PluginManager
    networks: NetworkManager

    @cached_property
    def _converters(self) -> Dict[Type, List[ConverterAPI]]:
        converters: Dict[Type, List[ConverterAPI]] = {
            ChecksumAddress: [],
            bytes: [hex_converter],
            int: [],
        }

        for plugin_name, (conversion_type, converter_class) in self.plugin_manager.converters:
            converter = converter_class(self.config.get_config(plugin_name), self.networks)

            if conversion_type not in converters:
                raise Exception(f"Cannot support converters that convert to {conversion_type}")

            converters[conversion_type].append(converter)

        return converters

    def is_type(self, value: Any, type: Type) -> bool:
        if type is ChecksumAddress and isinstance(value, str):
            return is_checksum_address(value)

        else:
            return isinstance(value, type)

    def convert(self, value: Any, type: Type) -> Any:
        if type not in self._converters:
            converter_types = ", ".join(map(lambda t: t.__name__, self._converters))
            raise Exception(f"ABI Type '{type}' must be one of [{converter_types}]")

        if self.is_type(value, type):
            return value

        for converter in self._converters[type]:
            if converter.is_convertible(value):
                return converter.convert(value)

        raise Exception(f"No conversion found for '{value}'")
