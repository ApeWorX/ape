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
