from pathlib import Path
from typing import Iterator, List, Optional, Type, Union

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
    def sign_message(self, msg: SignableMessage) -> Optional[SignedMessage]:
        ...

    def sign_transaction(self, txn: TransactionAPI) -> Optional[TransactionAPI]:
        # NOTE: Some accounts may not offer signing things
        return txn

    def call(self, txn: TransactionAPI) -> ReceiptAPI:
        txn.nonce = self.nonce
        txn.gas_limit = self.provider.estimate_gas_cost(txn)
        txn.gas_price = self.provider.gas_price

        if txn.gas_limit * txn.gas_price + txn.value > self.balance:
            raise Exception("Transfer value meets or exceeds account balance")

        signed_txn = self.sign_transaction(txn)

        if not signed_txn:
            raise Exception("User didn't sign!")

        return self.provider.send_transaction(signed_txn)

    def transfer(
        self,
        account: Union[str, "AddressAPI"],
        value: int = None,
        data: bytes = None,
    ) -> ReceiptAPI:
        txn = self._transaction_class(  # type: ignore
            sender=self.address,
            receiver=account.address if isinstance(account, AddressAPI) else account,
        )

        if data:
            txn.data = data

        if value:
            txn.value = value

        else:
            # NOTE: If `value` is `None`, send everything
            txn.value = self.balance - txn.gas_limit * txn.gas_price

        return self.call(txn)

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
