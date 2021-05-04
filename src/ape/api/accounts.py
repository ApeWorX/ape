from pathlib import Path
from typing import Iterator, Optional, Type

from eth_account.datastructures import SignedMessage  # type: ignore
from eth_account.messages import SignableMessage  # type: ignore

from ape.types import ContractType

from .address import AddressAPI
from .base import abstractdataclass, abstractmethod
from .contracts import ContractContainer, ContractInstance
from .providers import ReceiptAPI, TransactionAPI


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
        txn.gas_limit = self._active_provider.estimate_gas_cost(txn)
        txn.gas_price = self._active_provider.gas_price

        if txn.gas_limit * txn.gas_price + txn.value > self.balance:
            raise  # Transfer value meets or exceeds account balance

        txn = self.sign_transaction(txn)
        return self._active_provider.send_transaction(txn)

    def deploy(self, contract_type: ContractType, *args, **kwargs) -> ContractInstance:
        kwargs["sender"] = self.address
        c = ContractContainer(  # type: ignore
            provider=self._active_provider,
            contract_type=contract_type,
        )

        txn = c.build_deployment(*args, **kwargs)
        txn.nonce = self.nonce
        txn.gas_limit = self._active_provider.estimate_gas_cost(txn)
        txn.gas_price = self._active_provider.gas_price

        txn_cost = txn.gas_limit * txn.gas_price
        if "value" in kwargs:
            txn_cost += kwargs["value"]

        if txn_cost > self.balance:
            raise  # Transfer value meets or exceeds account balance

        txn = self.sign_transaction(txn)
        receipt = self._active_provider.send_transaction(txn)

        if not receipt.contract_address:
            raise  # `receipt.txn_hash` did not create a contract

        breakpoint()
        return ContractInstance(  # type: ignore
            address=receipt.contract_address,
            provider=self._active_provider,
            contract_type=contract_type,
        )


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
