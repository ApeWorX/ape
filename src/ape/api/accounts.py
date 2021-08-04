from pathlib import Path
from typing import Callable, Iterator, List, Optional, Type, Union

from ape.types import (
    AddressType,
    ContractType,
    MessageSignature,
    SignableMessage,
    TransactionSignature,
)
from ape.utils import cached_property

from .address import AddressAPI
from .base import abstractdataclass, abstractmethod
from .contracts import ContractContainer, ContractInstance
from .providers import ReceiptAPI, TransactionAPI


# NOTE: AddressAPI is a dataclass already
class AccountAPI(AddressAPI):
    container: "AccountContainerAPI"

    def __dir__(self) -> List[str]:
        # This displays methods to IPython on `a.[TAB]` tab completion
        return list(super(AddressAPI, self).__dir__()) + [
            "alias",
            "sign_message",
            "sign_transaction",
            "call",
            "transfer",
            "deploy",
        ]

    @property
    def alias(self) -> Optional[str]:
        """
        Override with whatever alias might want to use, if applicable
        """
        return None

    @abstractmethod
    def sign_message(self, msg: SignableMessage) -> Optional[MessageSignature]:
        ...

    @abstractmethod
    def sign_transaction(self, txn: TransactionAPI) -> Optional[TransactionSignature]:
        ...

    def call(self, txn: TransactionAPI, send_everything: bool = False) -> ReceiptAPI:
        # NOTE: Use "expected value" for Chain ID, so if it doesn't match actual, we raise
        txn.chain_id = self.provider.network.chain_id

        # NOTE: Allow overriding nonce, assume user understand what this does
        if txn.nonce is None:
            txn.nonce = self.nonce
        elif txn.nonce < self.nonce:
            raise Exception("Invalid nonce, will not publish!")

        # TODO: Add `GasEstimationAPI`
        if txn.gas_price is None:
            txn.gas_price = self.provider.gas_price
        # else: assume user specified a correct price, or will take too much time to confirm

        # NOTE: Allow overriding gas limit
        if txn.gas_limit is None:
            txn.gas_limit = 0  # NOTE: Need a starting estimate
            txn.gas_limit = self.provider.estimate_gas_cost(txn)
        # else: assume user specified the correct amount or txn will fail and waste gas

        if send_everything:
            txn.value = self.balance - txn.gas_limit * txn.gas_price

        if txn.gas_limit * txn.gas_price + txn.value > self.balance:
            raise Exception("Transfer value meets or exceeds account balance")

        txn.signature = self.sign_transaction(txn)

        if not txn.signature:
            raise Exception("User didn't sign!")

        return self.provider.send_transaction(txn)

    @cached_property
    def _convert(self) -> Callable:
        # NOTE: Need to differ loading this property
        from ape import convert

        return convert

    def transfer(
        self,
        account: Union[str, AddressType, "AddressAPI"],
        value: Union[str, int, None] = None,
        data: Union[bytes, str, None] = None,
        **kwargs,
    ) -> ReceiptAPI:
        txn = self._transaction_class(  # type: ignore
            sender=self.address,
            receiver=self._convert(account, AddressType),
            **kwargs,
        )

        if data:
            txn.data = self._convert(data, bytes)

        if value:
            txn.value = self._convert(value, int)

        return self.call(txn, send_everything=value is None)

    def deploy(self, contract_type: ContractType, *args, **kwargs) -> ContractInstance:
        c = ContractContainer(  # type: ignore
            _provider=self.provider,
            _contract_type=contract_type,
        )

        txn = c(*args, **kwargs)
        txn.sender = self.address
        receipt = self.call(txn)

        if not receipt.contract_address:
            raise Exception(f"{receipt.txn_hash} did not create a contract")

        return ContractInstance(  # type: ignore
            _provider=self.provider,
            _address=receipt.contract_address,
            _contract_type=contract_type,
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

    def __getitem__(self, address: AddressType) -> AccountAPI:
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

    def __setitem__(self, address: AddressType, account: AccountAPI):
        raise NotImplementedError("Must define this method to use `container.append(acct)`")

    def remove(self, account: AccountAPI):
        if not isinstance(account, self.account_type):
            raise Exception("Not the right type for this container")

        if account.address not in self:
            raise Exception("Account not in container")

        if account.alias and account.alias in self.aliases:
            raise Exception("Alias already in use")

        self.__delitem__(account.address)

    def __delitem__(self, address: AddressType):
        raise NotImplementedError("Must define this method to use `container.remove(acct)`")

    def __contains__(self, address: AddressType) -> bool:
        try:
            self.__getitem__(address)
            return True

        except IndexError:
            return False
