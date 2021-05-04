from typing import TYPE_CHECKING, Optional, Type

from .base import abstractdataclass, abstractmethod
from .providers import ProviderAPI, ReceiptAPI, TransactionAPI

if TYPE_CHECKING:
    from ape.managers.networks import NetworkManager


@abstractdataclass
class AddressAPI:
    _network_manager: Optional["NetworkManager"] = None

    @property
    def _active_provider(self) -> ProviderAPI:
        if not self._network_manager:
            raise Exception("Not wired correctly")

        if not self._network_manager.active_provider:
            raise Exception("Not connected to any network!")

        return self._network_manager.active_provider

    @property
    def _receipt_class(self) -> Type[ReceiptAPI]:
        return self._active_provider.network.ecosystem.receipt_class

    @property
    def _transaction_class(self) -> Type[TransactionAPI]:
        return self._active_provider.network.ecosystem.transaction_class

    @property
    @abstractmethod
    def address(self) -> str:
        ...

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} {self.address}>"

    def __str__(self) -> str:
        return self.address

    @property
    def nonce(self) -> int:
        return self._active_provider.get_nonce(self.address)

    @property
    def balance(self) -> int:
        return self._active_provider.get_balance(self.address)

    @property
    def code(self) -> bytes:
        # TODO: Explore caching this (based on `self.provider.network` and examining code)
        return self._active_provider.get_code(self.address)

    @property
    def codesize(self) -> int:
        return len(self.code)

    @property
    def is_contract(self) -> bool:
        return len(self.code) > 0


class Address(AddressAPI):
    _address: str

    @property
    def address(self) -> str:
        return self._address
