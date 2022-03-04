from typing import Any, Generic, TypeVar

from ape.utils import BaseInterfaceModel, abstractmethod

ConvertedType = TypeVar("ConvertedType")


class ConverterAPI(Generic[ConvertedType], BaseInterfaceModel):
    @abstractmethod
    def is_convertible(self, value: Any) -> bool:
        """
        Returns ``True`` if string value provided by ``value`` is convertible using
        :meth:`ape.api.convert.ConverterAPI.convert`.

        Args:
            value (str): The value to check.

        Returns:
            bool: ``True`` when the given value can be converted.
        """

    @abstractmethod
    def convert(self, value: Any) -> ConvertedType:
        """
        Convert the given value to the type specified as the generic for this class.
        Implementations of this API must throw a :class:`~ape.exceptions.ConversionError`
        when the item fails to convert properly.
        """
