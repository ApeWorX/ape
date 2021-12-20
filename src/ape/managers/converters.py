from typing import Any, Dict, List, Type

from dataclassy import dataclass
from eth_utils import is_checksum_address, is_hex, is_hex_address, to_checksum_address
from hexbytes import HexBytes

from ape.api import AddressAPI, ConverterAPI
from ape.exceptions import ConversionError
from ape.logging import logger
from ape.plugins import PluginManager
from ape.types import AddressType
from ape.utils import cached_property

from .config import ConfigManager
from .networks import NetworkManager


# NOTE: This utility converter ensures that all bytes args can accept hex too
class HexConverter(ConverterAPI):
    """
    A converter that converts ``str`` to ``HexBytes``.
    """

    def is_convertible(self, value: str) -> bool:
        return is_hex(value)

    def convert(self, value: str) -> bytes:
        """
        Convert the given value to ``HexBytes``.

        Args:
            value (str): The value to convert.

        Returns:
            bytes
        """

        return HexBytes(value)


hex_converter = HexConverter(None, None)  # type: ignore


class AddressAPIConverter(ConverterAPI):
    """
    A converter that converts an :class:`~ape.api.address.AddressAPI` to a
    :class:`~ape.types.AddressType`.
    """

    def is_convertible(self, value: Any) -> bool:
        return isinstance(value, AddressAPI)

    def convert(self, value: AddressAPI) -> AddressType:
        """
        Convert the given value to :class:`~ape.types.AddressType`.

        Args:
            value (str): The value to convert.

        Returns:
            :class:`~ape.types.AddressType`
        """

        return value.address


address_api_converter = AddressAPIConverter(None, None)  # type: ignore


class HexAddressConverter(ConverterAPI):
    """
    A converter that converts a checksummed address ``str`` to a
    :class:`~ape.types.AddressType`.
    """

    def is_convertible(self, value: str) -> bool:
        return isinstance(value, str) and is_hex_address(value) and not is_checksum_address(value)

    def convert(self, value: str) -> AddressType:
        """
        Convert the given value to a :class:`~ape.types.AddressType`.

        Args:
            value (str): The address ``str`` to convert.

        Returns:
            :class:`~ape.types.AddressType`
        """

        logger.warning(f"The value '{value}' is not in checksummed form.")
        return to_checksum_address(value)


hex_address_converter = HexAddressConverter(None, None)  # type: ignore


@dataclass
class ConversionManager:
    """
    A singleton that manages all the converters.

    **NOTE**: typically, users will not interact with this class directly,
    but rather its ``convert()`` method, which is accessible from
    the root ``ape`` namespace.

    Usage example::

        from ape import convert

        amount = convert("1 gwei", int)
    """

    config: ConfigManager
    plugin_manager: PluginManager
    networks: NetworkManager

    def __repr__(self):
        return "<ConversionManager>"

    @cached_property
    def _converters(self) -> Dict[Type, List[ConverterAPI]]:
        converters: Dict[Type, List[ConverterAPI]] = {
            AddressType: [address_api_converter, hex_address_converter],
            bytes: [hex_converter],
            int: [],
        }

        for plugin_name, (conversion_type, converter_class) in self.plugin_manager.converters:
            converter = converter_class(self.config.get_config(plugin_name), self.networks)

            if conversion_type not in converters:
                options = ", ".join([t.__name__ for t in converters])
                raise ConversionError(f"Type '{conversion_type}' must be one of [{options}].")

            converters[conversion_type].append(converter)

        return converters

    def is_type(self, value: Any, type: Type) -> bool:
        """
        Check if the value is the given type.
        If given an :class:`~ape.types.AddressType`, will also check
        that it is checksummed.

        Args:
            value (any): The value to check.
            type (type): The type to check against.

        Returns:
            bool: ``True`` when we consider the given value to be the given type.
        """

        if type is AddressType:
            return is_checksum_address(value)

        else:
            return isinstance(value, type)

    def convert(self, value: Any, type: Type) -> Any:
        """
        Convert the given value to the given type. This method accesses
        all :class:`~ape.api.convert.ConverterAPI` instances known to
        `ape`` and selects the appropriate one, so long that it exists.

        Raises:
            :class:`~ape.exceptions.ConversionError`: When there is not a registered
              converter for the given arguments.

        Args:
            value (any): The value to convert.
            type (type): The type to convert the value to.

        Returns:
            any: The same given value but with the new given type.
        """

        if type not in self._converters:
            options = ", ".join([t.__name__ for t in self._converters])
            raise ConversionError(f"Type '{type}' must be one of [{options}].")

        if self.is_type(value, type):
            return value

        for converter in self._converters[type]:
            if converter.is_convertible(value):
                return converter.convert(value)

        raise ConversionError(f"No conversion registered to handle '{value}'.")
