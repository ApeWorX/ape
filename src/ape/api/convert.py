from abc import ABC, abstractmethod
from typing import Any, Generic, TypeVar

from ape.utils.basemodel import BaseInterfaceModel

ConvertedType = TypeVar("ConvertedType")


class ConverterAPI(BaseInterfaceModel, Generic[ConvertedType]):
    @abstractmethod
    def is_convertible(self, value: Any) -> bool:
        """
        Returns ``True`` if string value provided by ``value`` is convertible using
        :meth:`ape.api.convert.ConverterAPI.convert`.

        Args:
            value (Any): The value to check.

        Returns:
            bool: ``True`` when the given value can be converted.
        """

    @abstractmethod
    def convert(self, value: Any) -> ConvertedType:
        """
        Convert the given value to the type specified as the generic for this class.
        Implementations of this API must throw a :class:`~ape.exceptions.ConversionError`
        when the item fails to convert properly.

        Usage example::

            from ape import convert
            from ape.types import AddressType

            convert("1 gwei", int)
            # 1000000000

            convert("1 ETH", int)
            # 1000000000000000000

            convert("0x283Af0B28c62C092C9727F1Ee09c02CA627EB7F5", bytes)
            # HexBytes('0x283af0b28c62c092c9727f1ee09c02ca627eb7f5')

            convert("vitalik.eth", AddressType)  # with ape-ens plugin installed
            # '0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045'

        """

    @property
    def name(self) -> str:
        """
        The calculated name of the converter class.
        Typically, it is the lowered prefix of the class without
        the "Converter" or "Conversions" suffix.
        """
        class_name = self.__class__.__name__
        name = class_name.replace("Converter", "").replace("Conversions", "")
        return name.lower()


class ConvertibleAPI(ABC):
    """
    Use this base-class mixin if you want your custom class to be convertible to a more basic type
    without having to register a converter plugin for it.
    """

    @abstractmethod
    def is_convertible(self, to_type: type) -> bool:
        """
        Returns ``True`` if ``self`` can be converted to ``to_type``.
        """

    @abstractmethod
    def convert_to(self, to_type: type) -> Any:
        """
        Convert ``self`` to the given type. Implementing classes _should_ raise ``ConversionError`` if not convertible.
        Ape's conversion system will **only** attempt to convert classes where ``.is_convertible()`` returns ``True``.
        """
