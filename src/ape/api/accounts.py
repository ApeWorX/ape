from abc import ABC, abstractmethod
from pathlib import Path
from typing import Iterator, List, Optional

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
    @property
    def alias(self) -> str:
        return ""

    @abstractmethod
    def sign_message(self, msg: SignableMessage) -> Optional[SignedMessage]:
        ...

    @abstractmethod
    def sign_transaction(self, txn: dict) -> Optional[SignedTransaction]:
        ...


class AccountContainerAPI(ABC):
    def __init__(self, DATA_FOLDER: Path):
        self.DATA_FOLDER = DATA_FOLDER

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


# NOTE: This class is an aggregated container for all of the registered containers
class Accounts(AccountContainerAPI):
    def __init__(self):
        # NOTE: Delayed loading of cached accounts (prevents circular imports)
        self._account_plugins: List[AccountContainerAPI] = None

    @property
    def account_plugins(self) -> Iterator[AccountContainerAPI]:
        if not self._account_plugins:
            from ape import DATA_FOLDER, plugins

            account_plugins = plugins.registered_plugins[plugins.AccountPlugin]
            self._account_plugins = [p.data(DATA_FOLDER / p.name) for p in account_plugins]

        for container in self._account_plugins:
            yield container

    @property
    def aliases(self) -> Iterator[str]:
        for container in self.account_plugins:
            for alias in container.aliases:
                yield alias

    def __len__(self) -> int:
        return sum(len(container) for container in self.account_plugins)

    def __iter__(self) -> Iterator[AccountAPI]:
        for container in self.account_plugins:
            for account in container:
                # TODO: Inject Web3
                yield account

    def load(self, alias: str) -> AccountAPI:
        if alias == "":
            raise ValueError("Cannot use empty string as alias!")

        for account in self:
            if account.alias == alias:
                return account

        raise IndexError(f"No account with alias `{alias}`.")

    def __getitem__(self, address: str) -> AccountAPI:
        for container in self.account_plugins:
            if address in container:
                return container[address]

        raise IndexError(f"No account with address `{address}`.")

    def __contains__(self, address: str) -> bool:
        return any(address in container for container in self.account_plugins)
