from abc import ABC, abstractmethod
from pathlib import Path
from typing import Iterator, Optional

from eth_account.datastructures import SignedMessage, SignedTransaction  # type: ignore
from eth_account.messages import SignableMessage  # type: ignore


class AddressAPI(ABC):
    @property
    @abstractmethod
    def address(self) -> str:
        ...

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} {self.address}>"

    def __str__(self) -> str:
        return self.address


class AccountAPI(AddressAPI, ABC):
    # Should be injected by container, so it has a link back
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


# NOTE: Should be singleton
class AccountContainerAPI(ABC):
    # Inject this constant into the class before instantiation
    _data_folder: Path

    @property
    def DATA_FOLDER(self) -> Path:
        assert self.__class__._data_folder is not None
        self.__class__._data_folder.mkdir(exist_ok=True)
        return self.__class__._data_folder

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
