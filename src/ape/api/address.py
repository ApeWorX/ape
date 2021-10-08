from typing import List, Optional, Type

from ape.types import AddressType

from ..exceptions import AddressError
from .base import abstractdataclass, abstractmethod
from .providers import ProviderAPI, ReceiptAPI, TransactionAPI


@abstractdataclass
class AddressAPI:
    _provider: Optional[ProviderAPI] = None

    @property
    def provider(self) -> ProviderAPI:
        if not self._provider:
            raise AddressError(
                f"Incorrectly implemented provider API for class {type(self).__name__}"
            )

        return self._provider

    @provider.setter
    def provider(self, value: ProviderAPI):
        self._provider = value

    @property
    def _receipt_class(self) -> Type[ReceiptAPI]:
        return self.provider.network.ecosystem.receipt_class

    @property
    def _transaction_class(self) -> Type[TransactionAPI]:
        return self.provider.network.ecosystem.transaction_class

    @property
    @abstractmethod
    def address(self) -> AddressType:
        ...

    def __dir__(self) -> List[str]:
        # This displays methods to IPython on `a.[TAB]` tab completion
        return [
            "address",
            "balance",
            "code",
            "codesize",
            "nonce",
            "is_contract",
            "provider",
        ]

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} {self.address}>"

    def __str__(self) -> str:
        return self.address

    @property
    def nonce(self) -> int:
        return self.provider.get_nonce(self.address)

    @property
    def balance(self) -> int:
        return self.provider.get_balance(self.address)

    @property
    def code(self) -> bytes:
        # TODO: Explore caching this (based on `self.provider.network` and examining code)
        return self.provider.get_code(self.address)

    @property
    def codesize(self) -> int:
        return len(self.code)

    @property
    def is_contract(self) -> bool:
        return len(self.code) > 0


class Address(AddressAPI):
    _address: AddressType

    @property
    def address(self) -> AddressType:
        return self._address
