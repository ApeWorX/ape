from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, Dict, List, Sequence, Tuple, Type, Union

from dateutil.parser import parse  # type: ignore
from eth_utils import (
    is_0x_prefixed,
    is_checksum_address,
    is_hex,
    is_hex_address,
    to_checksum_address,
    to_hex,
    to_int,
)
from ethpm_types import ConstructorABI, EventABI, HexBytes, MethodABI

from ape.api import ConverterAPI, TransactionAPI
from ape.api.address import BaseAddress
from ape.exceptions import ConversionError
from ape.types import AddressType
from ape.utils import cached_property

from .base import BaseManager


# NOTE: This utility converter ensures that all bytes args can accept hex too
class HexConverter(ConverterAPI):
    """
    A converter that converts ``str`` to ``HexBytes``.
    """

    def is_convertible(self, value: Any) -> bool:
        return (
            (isinstance(value, str) and is_hex(value) and is_0x_prefixed(value))
            or isinstance(value, bytes)
            or isinstance(value, int)
        )

    def convert(self, value: str) -> bytes:
        """
        Convert the given value to ``HexBytes``.

        Args:
            value (str): The value to convert.

        Returns:
            bytes
        """

        return HexBytes(value)


class HexIntConverter(ConverterAPI):
    """
    Convert hex values to integers.

    **NOTE** If value is a ``str``, it must begin with "0x".
    """

    def is_convertible(self, value: Any) -> bool:
        return (isinstance(value, str) and is_hex(value) and is_0x_prefixed(value)) or isinstance(
            value, bytes
        )

    def convert(self, value: Any) -> int:
        return to_int(HexBytes(value))


class StringIntConverter(ConverterAPI):
    def is_convertible(self, value: Any) -> bool:
        return isinstance(value, str) and not is_0x_prefixed(value) and value.isnumeric()

    def convert(self, value: str) -> int:
        return int(value)


class AddressAPIConverter(ConverterAPI):
    """
    A converter that converts an :class:`~ape.api.address.BaseAddress` to a ``AddressType``.
    """

    def is_convertible(self, value: Any) -> bool:
        return isinstance(value, BaseAddress)

    def convert(self, value: BaseAddress) -> AddressType:
        """
        Convert the given value to ``AddressType``.

        Args:
            value (str): The value to convert.

        Returns:
            ``AddressType``: An alias to
            `ChecksumAddress <https://eth-typing.readthedocs.io/en/latest/types.html#checksumaddress>`__.  # noqa: E501
        """

        return value.address


class HexAddressConverter(ConverterAPI):
    """
    A converter that converts a checksummed address ``str`` to a ``AddressType``.
    """

    def is_convertible(self, value: Any) -> bool:
        return isinstance(value, str) and is_hex_address(value) and not is_checksum_address(value)

    def convert(self, value: str) -> AddressType:
        """
        Convert the given value to a ``AddressType``.

        Args:
            value (str): The address ``str`` to convert.

        Returns:
            ``AddressType``
        """

        return to_checksum_address(value)


class BytesAddressConverter(ConverterAPI):
    """
    A converter that converts a raw bytes address to an ``AddressType``.
    """

    def is_convertible(self, value: Any) -> bool:
        return isinstance(value, bytes) and len(value) == 20

    def convert(self, value: bytes) -> AddressType:
        return to_checksum_address(value)


class IntAddressConverter(ConverterAPI):
    """
    A converter that converts an integer address to an ``AddressType``.
    """

    def is_convertible(self, value: Any) -> bool:
        return isinstance(value, int) and is_hex_address(to_hex(value))

    def convert(self, value: Any) -> AddressType:
        return to_checksum_address(to_hex(value))


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
            # Ignore already-primitive values and assume they are already converted
            # (since we don't know the type they are supposed to be, only that
            # they should be primitive). Also, ignore dicts because they are handled
            # at the ecosystem level.
            if (
                (isinstance(v, str) and is_hex(v))
                or isinstance(v, (int, bytes))
                or isinstance(v, dict)
            ):
                converted_value.append(v)
                continue

            # Try all of them to see if one converts it over (only use first one)
            conversion_found = False
            # NOTE: Double loop required because we might not know the exact type of the inner
            #       items. The UX of having to specify all inner items seemed poor as well.
            for typ in self.conversion_manager._converters:
                for check_fn, convert_fn in map(
                    lambda c: (c.is_convertible, c.convert),
                    self.conversion_manager._converters[typ],
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


class TimestampConverter(ConverterAPI):
    """
    Converts either a string, datetime object, or a timedelta object to a timestamp.
    No timezone required, but should be formatted to UTC.
    """

    def is_convertible(self, value: Union[str, datetime, timedelta]) -> bool:
        if not isinstance(value, (str, datetime, timedelta)):
            return False
        if isinstance(value, str):
            if " " not in value or len(value.split(" ")) > 2:
                return False
            else:
                try:
                    parse(value)
                except ValueError:
                    return False
        return True

    def convert(self, value: Union[str, datetime, timedelta]) -> int:
        if isinstance(value, str):
            return int(parse(value).replace(tzinfo=timezone.utc).timestamp())
        elif isinstance(value, datetime):
            return int(value.replace(tzinfo=timezone.utc).timestamp())
        elif isinstance(value, timedelta):
            return int((datetime.now(timezone.utc) + value).timestamp())
        else:
            raise ConversionError()


class ConversionManager(BaseManager):
    """
    A singleton that manages all the converters.

    **NOTE**: typically, users will not interact with this class directly,
    but rather its ``convert()`` method, which is accessible from
    the root ``ape`` namespace.

    Usage example::

        from ape import convert

        amount = convert("1 gwei", int)
    """

    def __repr__(self):
        return f"<{self.__class__.__name__}>"

    @cached_property
    def _converters(self) -> Dict[Type, List[ConverterAPI]]:
        converters: Dict[Type, List[ConverterAPI]] = {
            AddressType: [
                AddressAPIConverter(),
                BytesAddressConverter(),
                HexAddressConverter(),
                IntAddressConverter(),
            ],
            bytes: [HexConverter()],
            int: [TimestampConverter(), HexIntConverter(), StringIntConverter()],
            Decimal: [],
            list: [ListTupleConverter()],
            tuple: [ListTupleConverter()],
            bool: [],
            str: [],
        }

        for plugin_name, (conversion_type, converter_class) in self.plugin_manager.converters:
            converter = converter_class()
            if conversion_type not in converters:
                options = ", ".join([t.__name__ for t in converters])
                raise ConversionError(f"Type '{conversion_type}' must be one of [{options}].")

            converters[conversion_type].append(converter)

        return converters

    def is_type(self, value: Any, type: Type) -> bool:
        """
        Check if the value is the given type.
        If given an ``AddressType``, will also check
        that it is checksummed.

        Args:
            value (any): The value to check.
            type (type): The type to check against.

        Returns:
            bool: ``True`` when we consider the given value to be the given type.
        """

        return is_checksum_address(value) if type is AddressType else isinstance(value, type)

    def convert(self, value: Any, type: Union[Type, Tuple, List]) -> Any:
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

        if isinstance(value, (list, tuple)) and isinstance(type, tuple):
            # We expected to convert a tuple type, so convert each item in the tuple.
            # NOTE: We allow values to be a list, just in case it is a list
            return [self.convert(v, t) for v, t in zip(value, type)]

        elif isinstance(value, list) and isinstance(type, list) and len(type) == 1:
            # We expected to convert an array type(dynamic or static),
            # so convert each item in the list.
            # NOTE: type for static and dynamic array is a single item
            #  list containing the type of the array.
            return [self.convert(v, type[0]) for v in value]

        elif isinstance(type, (list, tuple)):
            raise ConversionError(
                f"Value '{value}' must be a list or tuple when given multiple types."
            )

        elif type not in self._converters:
            options = ", ".join([t.__name__ for t in self._converters])
            raise ConversionError(f"Type '{type}' must be one of [{options}].")

        elif self.is_type(value, type) and not isinstance(value, (list, tuple)):
            # NOTE: Always process lists and tuples
            return value

        for converter in self._converters[type]:
            if not converter.is_convertible(value):
                continue

            try:
                return converter.convert(value)
            except Exception as err:
                try:
                    error_value = f" '{value}' "
                except Exception:
                    error_value = " "

                message = f"Failed to convert{error_value}using '{converter.__class__.__name__}'."
                raise ConversionError(message) from err

        raise ConversionError(f"No conversion registered to handle '{value}'.")

    def convert_method_args(
        self,
        abi: Union[MethodABI, ConstructorABI, EventABI],
        arguments: Sequence[Any],
    ):
        input_types = [i.canonical_type for i in abi.inputs]
        pre_processed_args = []
        for ipt, argument in zip(input_types, arguments):
            # Handle primitive-addresses separately since they may not occur
            # on the tuple-conversion if they are integers or bytes.
            if str(ipt) == "address":
                converted_value = self.convert(argument, AddressType)
                pre_processed_args.append(converted_value)
            else:
                pre_processed_args.append(argument)

        return self.convert(pre_processed_args, tuple)

    def convert_method_kwargs(self, kwargs) -> Dict:
        fields = TransactionAPI.__fields__

        kwargs_to_convert = {k: v for k, v in kwargs.items() if k == "sender" or k in fields}
        converted_fields = {
            k: self.convert(v, AddressType if k == "sender" else fields[k].type_)
            for k, v in kwargs_to_convert.items()
        }
        return {**kwargs, **converted_fields}
