from typing import TYPE_CHECKING, Any, Generic, TypeVar

from ape.utils import abstractdataclass, abstractmethod

from .config import ConfigItem

if TYPE_CHECKING:
    from ape.managers.converters import ConversionManager
    from ape.managers.networks import NetworkManager

ConvertedType = TypeVar("ConvertedType")


@abstractdataclass
class ConverterAPI(Generic[ConvertedType]):
    # NOTE: In case we need to store info e.g. tokenlists
    config: ConfigItem

    # NOTE: In case we need access to a network e.g. ENS
    networks: "NetworkManager"

    converter: "ConversionManager"

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
