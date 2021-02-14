from typing import Iterator, Optional

from eth_account.messages import SignableMessage  # type: ignore
from eth_account.datastructures import SignedMessage, SignedTransaction  # type: ignore


class AccountAPI:
    @property
    def address(self) -> str:
        ...

    def sign_message(self, msg: SignableMessage) -> Optional[SignedMessage]:
        ...

    def sign_transaction(self, txn: dict) -> Optional[SignedTransaction]:
        ...

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} {self.address}>"

    def __str__(self) -> str:
        return self.address


class AccountControllerAPI:
    def __len__(self) -> int:
        ...

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
