from abc import ABCMeta, abstractmethod
from pathlib import Path
from typing import Iterator, Optional, Type

from dataclassy import dataclass
from eth_account.datastructures import SignedMessage, SignedTransaction  # type: ignore
from eth_account.messages import SignableMessage  # type: ignore


@dataclass
class AddressAPI(metaclass=ABCMeta):
    # TODO add `network: NetworkController`

    @property
    @abstractmethod
    def address(self) -> str:
        ...

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} {self.address}>"

    def __str__(self) -> str:
        return self.address


# NOTE: AddressAPI is a dataclass already
class AccountAPI(AddressAPI):
    container: "AccountContainerAPI"

    @property
    def alias(self) -> str:
        return ""

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

    def __contains__(self, address: str) -> bool:
        try:
            self.__getitem__(address)
            return True

        except IndexError:
            return False
