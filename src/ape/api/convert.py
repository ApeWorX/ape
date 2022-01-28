from typing import TYPE_CHECKING, Any, ClassVar, Generic, TypeVar

from ape.utils import AbstractBaseModel, abstractmethod, injected_before_use

from .config import ConfigItem

if TYPE_CHECKING:
    from ape.managers.converters import ConversionManager
    from ape.managers.networks import NetworkManager

ConvertedType = TypeVar("ConvertedType")


class ConverterAPI(Generic[ConvertedType], AbstractBaseModel):
    # NOTE: In case we need to store info e.g. tokenlists
    config: ClassVar[ConfigItem] = injected_before_use()  # type: ignore

    # NOTE: In case we need access to a network e.g. ENS
    networks: ClassVar["NetworkManager"] = injected_before_use()  # type: ignore

    converter: ClassVar["ConversionManager"] = injected_before_use()  # type: ignore

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
