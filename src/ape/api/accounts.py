from pathlib import Path
from typing import TYPE_CHECKING, Iterator, Optional, Type

from eth_account.datastructures import SignedMessage  # type: ignore
from eth_account.messages import SignableMessage  # type: ignore

from .base import abstractdataclass, abstractmethod

if TYPE_CHECKING:
    from ape.managers.networks import NetworkManager

from .providers import ProviderAPI, ReceiptAPI, TransactionAPI


@abstractdataclass
class AddressAPI:
    network_manager: Optional["NetworkManager"] = None

    @property
    def _provider(self) -> ProviderAPI:
        if not self.network_manager:
            raise Exception("Not wired correctly")

        if not self.network_manager.active_provider:
            raise Exception("Not connected to any network!")

        return self.network_manager.active_provider

    @property
    def _receipt_class(self) -> Type[ReceiptAPI]:
        return self._provider.network.ecosystem.receipt_class

    @property
    def _transaction_class(self) -> Type[TransactionAPI]:
        return self._provider.network.ecosystem.transaction_class

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

    def sign_transaction(self, txn: TransactionAPI) -> TransactionAPI:
        # NOTE: Some accounts may not offer signing things
        return txn

    def transfer(self, account: "AddressAPI", value: int = None, data: bytes = None) -> ReceiptAPI:
        txn = self._transaction_class(  # type: ignore
            sender=self.address,
            receiver=account.address,
            nonce=self.nonce,
        )

        if data:
            txn.data = data

        if value:
            txn.value = value

        else:
            # NOTE: If `value` is `None`, send everything
            txn.value = self.balance - txn.gas_limit * txn.gas_price

        return self.call(txn)

    def call(self, txn: TransactionAPI) -> ReceiptAPI:
        txn.gas_limit = self._provider.estimate_gas_cost(txn)
        txn.gas_price = self._provider.gas_price

        if txn.gas_limit * txn.gas_price + txn.value > self.balance:
            raise  # Transfer value meets or exceeds account balance

        txn = self.sign_transaction(txn)
        return self._provider.send_transaction(txn)


@abstractdataclass
class AccountContainerAPI:
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
            raise Exception("Not the right type for this container")

        if account.address in self:
            raise Exception("Account already in container")

        if account.alias and account.alias in self.aliases:
            raise Exception("Alias already in use")

        self.__setitem__(account.address, account)

    def __setitem__(self, address: str, account: AccountAPI):
        raise NotImplementedError("Must define this method to use `container.append(acct)`")

    def remove(self, account: AccountAPI):
        if not isinstance(account, self.account_type):
            raise Exception("Not the right type for this container")

        if account.address not in self:
            raise Exception("Account not in container")

        if account.alias and account.alias in self.aliases:
            raise Exception("Alias already in use")

        self.__delitem__(account.address)

    def __delitem__(self, address: str):
        raise NotImplementedError("Must define this method to use `container.remove(acct)`")

    def __contains__(self, address: str) -> bool:
        try:
            self.__getitem__(address)
            return True

        except IndexError:
            return False
