from decimal import Decimal
from typing import Any, Dict, List, Tuple, Type, Union

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

    def is_convertible(self, value: Any) -> bool:
        return isinstance(value, str) and is_hex(value)

    def convert(self, value: str) -> bytes:
        """
        Convert the given value to ``HexBytes``.

        Args:
            value (str): The value to convert.

        Returns:
            bytes
        """

        return HexBytes(value)


hex_converter = HexConverter(None, None, None)  # type: ignore


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


address_api_converter = AddressAPIConverter(None, None, None)  # type: ignore


class HexAddressConverter(ConverterAPI):
    """
    A converter that converts a checksummed address ``str`` to a
    :class:`~ape.types.AddressType`.
    """

    def is_convertible(self, value: Any) -> bool:
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


hex_address_converter = HexAddressConverter(None, None, None)  # type: ignore


class ListTupleConverter(ConverterAPI):
    """
    A converter that converts all items in a tuple or list recursively.
    """

    def is_convertible(self, value: Any) -> bool:
        return isinstance(value, (list, tuple))

    def convert(self, value: Union[List, Tuple]) -> Union[List, Tuple]:
        """
        Convert the items inside the given list or tuple.

        Args:
            value (Union[List, Tuple]): The collection to convert.

        Returns:
            Union[list, tuple]: Depending on the input
        """

        converted_value: List[Any] = []

        for v in value:
            # Try all of them to see if one converts it over (only use first one)
            conversion_found = False
            # NOTE: Double loop required because we might not know the exact type of the inner
            #       items. The UX of having to specify all inner items seemed poor as well.
            for typ in self.converter._converters:
                for check_fn, convert_fn in map(
                    lambda c: (c.is_convertible, c.convert), self.converter._converters[typ]
                ):
                    if check_fn(v):
                        converted_value.append(convert_fn(v))
                        conversion_found = True
                        break

                if conversion_found:
                    break

            if not conversion_found:
                # NOTE: If no conversions found, just insert the original
                converted_value.append(v)

        return value.__class__(converted_value)


list_tuple_converter = ListTupleConverter(None, None, None)  # type: ignore


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
        list_tuple_converter.converter = self  # Splice this in (no need for the rest)
        converters: Dict[Type, List[ConverterAPI]] = {
            AddressType: [address_api_converter, hex_address_converter],
            bytes: [hex_converter],
            int: [],
            Decimal: [],
            list: [list_tuple_converter],
            tuple: [list_tuple_converter],
        }

        for plugin_name, (conversion_type, converter_class) in self.plugin_manager.converters:
            converter = converter_class(self.config.get_config(plugin_name), self.networks, self)

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

        if self.is_type(value, type) and not isinstance(value, (list, tuple)):
            # NOTE: Always process lists and tuples
            return value

        for converter in self._converters[type]:
            if converter.is_convertible(value):
                return converter.convert(value)

        raise ConversionError(f"No conversion registered to handle '{value}'.")
