from typing import TYPE_CHECKING, Any, Generic, TypeVar

from .base import abstractdataclass, abstractmethod
from .config import ConfigItem

if TYPE_CHECKING:
    from ape.managers.networks import NetworkManager

ConvertedType = TypeVar("ConvertedType")


@abstractdataclass
class ConverterAPI(Generic[ConvertedType]):
    # NOTE: In case we need to store info e.g. tokenlists
    config: ConfigItem

    # NOTE: In case we need access to a network e.g. ENS
    networks: "NetworkManager"

    @abstractmethod
    def is_convertible(self, value: Any) -> bool:
        """
        Returns `True` if string value provided by `value` is convertible using
        `self.convert(value)`
        """

    @abstractmethod
    def convert(self, value: Any) -> ConvertedType:
        """
        Implements any conversion logic on `value` to produce `ABIType`.

        Must throw if not convertible.
        """
