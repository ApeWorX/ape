from abc import abstractmethod
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

            convert("vitalik.eth", AddressType) # with ape-ens plugin installed
            # '0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045'

        """
