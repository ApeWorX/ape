import re
from collections.abc import Iterable, Sequence
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from functools import cached_property
from typing import Any, Union

from dateutil.parser import parse
from eth_pydantic_types import Address, HexBytes
from eth_typing.evm import ChecksumAddress
from eth_utils import (
    is_0x_prefixed,
    is_checksum_address,
    is_hex,
    is_hex_address,
    to_checksum_address,
    to_int,
)
from ethpm_types import ConstructorABI, EventABI, MethodABI

from ape.api.address import BaseAddress
from ape.api.convert import ConverterAPI
from ape.api.transactions import TransactionAPI
from ape.exceptions import ConversionError
from ape.logging import logger
from ape.types.address import AddressType
from ape.utils.misc import log_instead_of_fail

from .base import BaseManager


class HexConverter(ConverterAPI):
    """
    A converter that converts ``str`` to ``HexBytes``.
    NOTE: This utility converter ensures that all bytes args can accept hex too
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


class HexIterableConverter(ConverterAPI):
    """
    Convert list of hex values to single concatenated ``HexBytes`` value.
    """

    def is_convertible(self, value: Any) -> bool:
        return isinstance(value, Iterable) and all(isinstance(v, bytes) or is_hex(v) for v in value)

    def convert(self, value: Any) -> bytes:
        return HexBytes(b"".join(HexBytes(v) for v in value))


class StringIntConverter(ConverterAPI):
    def is_convertible(self, value: Any) -> bool:
        return isinstance(value, str) and not is_0x_prefixed(value) and value.isnumeric()

    def convert(self, value: str) -> int:
        return int(value)


class AccountIntConverter(ConverterAPI):
    def is_convertible(self, value: Any) -> bool:
        return isinstance(value, BaseAddress)

    def convert(self, value: BaseAddress) -> int:
        return self.conversion_manager.convert(value.address, int)


class AddressAPIConverter(ConverterAPI):
    """
    A converter that converts an :class:`~ape.api.address.BaseAddress`
    to a :class`~ape.types.address.AddressType`.
    """

    def is_convertible(self, value: Any) -> bool:
        return isinstance(value, BaseAddress)

    def convert(self, value: BaseAddress) -> AddressType:
        """
        Convert the given value to :class:`~ape.types.address.AddressType`.

        Args:
            value (str): The value to convert.

        Returns:
            :class:`~ape.types.address.AddressType`: An alias to
            `ChecksumAddress <https://eth-typing.readthedocs.io/en/latest/types.html#checksumaddress>`__.  # noqa: E501
        """

        return value.address


class HexAddressConverter(ConverterAPI):
    """
    A converter that converts a checksummed address ``str`` to a
    :class:`~ape.types.address.AddressType`.
    """

    def is_convertible(self, value: Any) -> bool:
        return isinstance(value, str) and is_hex_address(value) and not is_checksum_address(value)

    def convert(self, value: str) -> AddressType:
        """
        Convert the given value to a :class:`~ape.types.address.AddressType`.

        Args:
            value (str): The address ``str`` to convert.

        Returns:
            :class:`~ape.types.address.AddressType`
        """

        return AddressType(to_checksum_address(value))


class BytesAddressConverter(ConverterAPI):
    """
    A converter that converts a raw bytes address to an :class:`~ape.types.address.AddressType`.
    """

    def is_convertible(self, value: Any) -> bool:
        return isinstance(value, bytes) and len(value) == 20

    def convert(self, value: bytes) -> AddressType:
        return to_checksum_address(value)


class IntAddressConverter(ConverterAPI):
    """
    A converter that converts an integer address to an :class:`~ape.types.address.AddressType`.
    """

    _cache: dict[int, Union[AddressType, bool]] = {}

    def is_convertible(self, value: Any) -> bool:
        if not isinstance(value, int):
            return False
        elif isinstance(self._cache.get(value), str):
            return True

        val = self._convert(value)
        self._cache[value] = val
        return isinstance(val, str)

    def convert(self, value: Any) -> AddressType:
        err_msg = f"Failed to convert '{value}' to 'AddressType'."
        if cached_val := self._cache.get(value):
            if not isinstance(cached_val, str):
                # Shouldn't get here in normal execution.
                raise ConversionError(err_msg)

            return cached_val

        # Shouldn't get here in normal execution.
        res = self._convert(value)
        self._cache[value] = res

        if not isinstance(res, str):
            raise ConversionError(err_msg)

        return res

    def _convert(self, value: int) -> Union[AddressType, bool]:
        try:
            val = Address.__eth_pydantic_validate__(value)
        except Exception:
            return False

        return AddressType(to_checksum_address(val))


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


class StringDecimalConverter(ConverterAPI):
    """
    Convert string-formatted floating point values to `Decimal` type.
    """

    def is_convertible(self, value: Any) -> bool:
        # Matches only string-formatted floats with an optional sign character (+/-).
        # Leading and trailing zeros are required.
        # NOTE: `re.fullmatch` will only match the full string, so "1.0 ether" and "10.0 USDC"
        # will not be identified as convertible.
        return isinstance(value, str) and re.fullmatch(r"[+-]?\d+\.\d+", value) is not None

    def convert(self, value: str) -> Decimal:
        return Decimal(value)


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

    @log_instead_of_fail(default="<DependencyAPI>")
    def __repr__(self) -> str:
        return f"<{ConversionManager.__name__}>"

    @cached_property
    def _converters(self) -> dict[type, list[ConverterAPI]]:
        converters: dict[type, list[ConverterAPI]] = {
            AddressType: [
                AddressAPIConverter(),
                BytesAddressConverter(),
                HexAddressConverter(),
                IntAddressConverter(),
            ],
            bytes: [
                HexConverter(),
                HexIterableConverter(),
            ],
            int: [
                TimestampConverter(),
                HexIntConverter(),
                StringIntConverter(),
                AccountIntConverter(),
            ],
            Decimal: [StringDecimalConverter()],
            bool: [],
            str: [],
        }

        for plugin_name, (conversion_type, converter_class) in self.plugin_manager.converters:
            converter = converter_class()
            if conversion_type is ChecksumAddress:
                converters[AddressType].append(converter)
                return converters

            elif conversion_type not in converters:
                options = ", ".join([_get_type_name_from_type(t) for t in converters])
                raise ConversionError(f"Type '{conversion_type}' must be one of [{options}].")

            converters[conversion_type].append(converter)

        return converters

    def is_type(self, value: Any, to_type: type) -> bool:
        """
        Check if the value is the given type.
        If given an :class:`~ape.types.address.AddressType`, will also check
        that it is checksummed.

        Args:
            value (any): The value to check.
            to_type (type): The type to check against.

        Returns:
            bool: ``True`` when we consider the given value to be the given type.
        """
        return is_checksum_address(value) if to_type is AddressType else isinstance(value, to_type)

    def convert(self, value: Any, to_type: Union[type, tuple, list]) -> Any:
        """
        Convert the given value to the given type. This method accesses
        all :class:`~ape.api.convert.ConverterAPI` instances known to
        `ape`` and selects the appropriate one, so long that it exists.

        Raises:
            :class:`~ape.exceptions.ConversionError`: When there is not a registered
              converter for the given arguments.

        Args:
            value (any): The value to convert.
            to_type (to_type): The type to convert the value to.

        Returns:
            any: The same given value but with the new given type.
        """

        if isinstance(value, (list, tuple)) and isinstance(to_type, tuple):
            # We expected to convert a tuple type, so convert each item in the tuple.
            # NOTE: We allow values to be a list, just in case it is a list
            return [self.convert(v, t) for v, t in zip(value, to_type)]

        elif isinstance(value, (list, tuple)) and isinstance(to_type, list) and len(to_type) == 1:
            # We expected to convert an array type(dynamic or static),
            # so convert each item in the list.
            # NOTE: type for static and dynamic array is a single item
            #  list containing the type of the array.
            return [self.convert(v, to_type[0]) for v in value]

        elif isinstance(to_type, (list, tuple)):
            raise ConversionError(
                f"Value '{value}' must be a list or tuple when given multiple types."
            )

        elif to_type is ChecksumAddress:
            # Use our Annotated alias.
            return self.convert(value, AddressType)

        elif to_type not in self._converters:
            options = ", ".join([_get_type_name_from_type(t) for t in self._converters])
            raise ConversionError(f"Type '{to_type}' must be one of [{options}].")

        elif self.is_type(value, to_type) and not isinstance(value, (list, tuple)):
            # NOTE: Always process lists and tuples
            return value

        for converter in self._converters[to_type]:
            try:
                is_convertible = converter.is_convertible(value)
            except Exception as err:
                # If errors while checking if we can convert, log the error
                # and assume it's not convertible.
                converter_name = converter.__class__.__name__
                msg = f"Issue while checking `{converter_name}.is_convertible()`: {err}"
                logger.error(msg)
                continue

            if not is_convertible:
                continue

            try:
                return converter.convert(value)
            except Exception as err:
                try:
                    error_value = f" '{value}' (type={type(value)}) "
                except Exception:
                    error_value = " "

                message = f"Failed to convert{error_value}"
                if converter_type_name := getattr(type(converter), "__name__", None):
                    message = f"{message}using '{converter_type_name}'."

                raise ConversionError(message) from err

        raise ConversionError(f"No conversion registered to handle '{value}'.")

    def convert_method_args(
        self,
        abi: Union[MethodABI, ConstructorABI, EventABI],
        arguments: Sequence[Any],
    ):
        input_types = [i.canonical_type for i in abi.inputs]
        converted_arguments = []
        for ipt, argument in zip(input_types, arguments):
            # Handle primitive-addresses separately since they may not occur
            # on the tuple-conversion if they are integers or bytes.
            if str(ipt) == "address":
                converted_value = self.convert(argument, AddressType)
                converted_arguments.append(converted_value)
            else:
                converted_arguments.append(argument)

        return converted_arguments

    def convert_method_kwargs(self, kwargs) -> dict:
        fields = TransactionAPI.model_fields

        def get_real_type(type_):
            all_types = getattr(type_, "_typevar_types", [])
            if not all_types or not isinstance(all_types, (list, tuple)):
                return type_

            # Filter out None
            valid_types = [t for t in all_types if t is not None]
            if len(valid_types) == 1:
                # This is something like Optional[int],
                # however, if the user provides a value,
                # we want to convert to the non-optional type.
                return valid_types[0]

            # Not sure if this is possible; the converter may fail.
            return valid_types

        annotations = {name: get_real_type(f.annotation) for name, f in fields.items()}
        kwargs_to_convert = {k: v for k, v in kwargs.items() if k == "sender" or k in fields}
        converted_fields = {}
        for field_name, value in kwargs_to_convert.items():
            type_ = AddressType if field_name == "sender" else annotations.get(field_name)
            if type_:
                try:
                    converted_value = self.convert(value, type_)
                except ConversionError:
                    # Ignore conversion errors and use the values as-is.
                    converted_value = value

            else:
                converted_value = value

            converted_fields[field_name] = converted_value

        return {**kwargs, **converted_fields}


def _get_type_name_from_type(var_type: type) -> str:
    if hasattr(var_type, "__args__") and var_type.__args__:
        # Is Annotated
        real_type = var_type.__args__[0]
        return _get_type_name_from_type(real_type)

    elif var_type is ChecksumAddress:
        return "AddressType"  # Use our alias

    elif hasattr(var_type, "__name__"):
        return var_type.__name__

    else:
        message = "Unable to deduce type name"
        try:
            str_value = f"{var_type}"
        except Exception:
            str_value = ""

        if str_value:
            message = f"{message} for {str_value}"

        raise TypeError(f"{message}.")
