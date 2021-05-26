from abc import ABCMeta, abstractmethod
from pathlib import Path
from typing import TYPE_CHECKING, Iterator, Optional, Type

from dataclassy import dataclass
from eth_account.datastructures import SignedMessage  # type: ignore
from eth_account.datastructures import SignedTransaction
from eth_account.messages import SignableMessage  # type: ignore

if TYPE_CHECKING:
    from ape.managers.networks import NetworkManager


@dataclass
class AddressAPI(metaclass=ABCMeta):
    network_manager: Optional["NetworkManager"] = None

    @property
    def _provider(self):
        if not self.network_manager:
            raise  # Not wired correctly

        if not self.network_manager.active_provider:
            raise  # Not connected to any network!

        return self.network_manager.active_provider

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
        return self._provider.get_nonce(self.address)

    @property
    def balance(self) -> int:
        return self._provider.get_balance(self.address)

    @property
    def code(self) -> bytes:
        # TODO: Explore caching this (based on `self.provider.network` and examining code)
        return self._provider.get_code(self.address)

    @property
    def codesize(self) -> int:
        return len(self.code)

    @property
    def is_contract(self) -> bool:
        return len(self.code) > 0


# NOTE: AddressAPI is a dataclass already
class AccountAPI(AddressAPI):
    container: "AccountContainerAPI"

    @property
    def alias(self) -> Optional[str]:
        """
        Override with whatever alias might want to use, if applicable
        """
        return None

    @abstractmethod
    def sign_message(self, msg: SignableMessage) -> Optional[SignedMessage]:
        ...

    @abstractmethod
    def sign_transaction(self, txn: dict) -> Optional[SignedTransaction]:
        ...


@dataclass
class AccountContainerAPI(metaclass=ABCMeta):
    data_folder: Path
    account_type: Type[AccountAPI]

    @property
    @abstractmethod
    def aliases(self) -> Iterator[str]:
        ...

    @abstractmethod
    def __len__(self) -> int:
        ...

    @abstractmethod
    def __iter__(self) -> Iterator[AccountAPI]:
        ...

    def __getitem__(self, address: str) -> AccountAPI:
        for account in self.__iter__():
            if account.address == address:
                return account

        raise IndexError(f"No local account {address}.")

    def append(self, account: AccountAPI):
        if not isinstance(account, self.account_type):
            raise  # Not the right type for this container

        if account in self:
            raise  # Account already in container

        if account.alias and account.alias in self.aliases:
            raise  # Alias already in use

        self.__setitem__(account.address, account)

    @abstractmethod
    def __setitem__(self, address: str, account: AccountAPI):
        raise NotImplementedError("Must define this method to use `container.append(...)`")

    def __contains__(self, address: str) -> bool:
        try:
            self.__getitem__(address)
            return True

        except IndexError:
            return False
