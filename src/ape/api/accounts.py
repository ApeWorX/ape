from pathlib import Path
from typing import TYPE_CHECKING, Callable, Iterator, List, Optional, Type, Union

from ape.exceptions import AccountsError, AliasAlreadyInUseError, SignatureError
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
from .providers import ReceiptAPI, TransactionAPI, TransactionType

if TYPE_CHECKING:
    from ape.managers.config import ConfigManager


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
        """
        Signs the given message.

        Args:
          msg (:class:`~eth_account.messages.SignableMessage`): The message to sign.

        Returns:
          :class:`~ape.types.signatures.MessageSignature` (optional): The signed message.
        """

    @abstractmethod
    def sign_transaction(self, txn: TransactionAPI) -> Optional[TransactionSignature]:
        """
        Signs the given transaction.

        Args:
          txn (:class:`~ape.api.providers.TransactionAPI`): The transaction to sign.

        Returns:
          :class:`~ape.types.signatures.TransactionSignature` (optional): The signed transaction.
        """

    def call(self, txn: TransactionAPI, send_everything: bool = False) -> ReceiptAPI:
        # NOTE: Use "expected value" for Chain ID, so if it doesn't match actual, we raise
        txn.chain_id = self.provider.network.chain_id

        # NOTE: Allow overriding nonce, assume user understand what this does
        if txn.nonce is None:
            txn.nonce = self.nonce
        elif txn.nonce < self.nonce:
            raise AccountsError("Invalid nonce, will not publish.")

        txn_type = TransactionType(txn.type)
        if txn_type == TransactionType.STATIC and txn.gas_price is None:  # type: ignore
            txn.gas_price = self.provider.gas_price  # type: ignore
        elif txn_type == TransactionType.DYNAMIC:
            if txn.max_priority_fee is None:  # type: ignore
                txn.max_priority_fee = self.provider.priority_fee  # type: ignore

            if txn.max_fee is None:
                txn.max_fee = self.provider.base_fee + txn.max_priority_fee
            # else: Assume user specified the correct amount or txn will fail and waste gas

        if txn.gas_limit is None:
            txn.gas_limit = self.provider.estimate_gas_cost(txn)
        # else: Assume user specified the correct amount or txn will fail and waste gas

        if send_everything:
            txn.value = self.balance - txn.max_fee

        if txn.total_transfer_value > self.balance:
            raise AccountsError(
                "Transfer value meets or exceeds account balance.\n"
                "Are you using the correct provider/account combination?\n"
                f"(transfer_value={txn.total_transfer_value}, balance={self.balance})."
            )

        txn.signature = self.sign_transaction(txn)
        if not txn.signature:
            raise SignatureError("The transaction was not signed.")

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
            raise AccountsError(f"'{receipt.txn_hash}' did not create a contract.")

        return ContractInstance(  # type: ignore
            _provider=self.provider,
            _address=receipt.contract_address,
            _contract_type=contract_type,
        )


@abstractdataclass
class AccountContainerAPI:
    data_folder: Path
    account_type: Type[AccountAPI]
    config_manager: "ConfigManager"

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
        self._verify_account_type(account)

        if account.address in self:
            raise AccountsError(f"Account '{account.address}' already in container.")

        self._verify_unused_alias(account)

        self.__setitem__(account.address, account)

    def __setitem__(self, address: AddressType, account: AccountAPI):
        raise NotImplementedError("Must define this method to use `container.append(acct)`.")

    def remove(self, account: AccountAPI):
        self._verify_account_type(account)

        if account.address not in self:
            raise AccountsError(f"Account '{account.address}' not known.")

        self.__delitem__(account.address)

    def __delitem__(self, address: AddressType):
        raise NotImplementedError("Must define this method to use `container.remove(acct)`.")

    def __contains__(self, address: AddressType) -> bool:
        try:
            self.__getitem__(address)
            return True

        except IndexError:
            return False

    def _verify_account_type(self, account):
        if not isinstance(account, self.account_type):
            message = (
                f"Container '{type(account).__name__}' is an incorrect "
                f"type for container '{type(self.account_type).__name__}'."
            )
            raise AccountsError(message)

    def _verify_unused_alias(self, account):
        if account.alias and account.alias in self.aliases:
            raise AliasAlreadyInUseError(account.alias)


class TestAccountContainerAPI(AccountContainerAPI):
    """
    Test account containers for ``ape test`` should implement
    this API instead of ``AccountContainerAPI`` directly. This
    is how they show up in the ``accounts`` test fixture.
    """


class TestAccountAPI(AccountAPI):
    """
    Test accounts for ``ape test`` should implement this API
    instead of ``AccountAPI`` directly. This is how they show
    up in the ``accounts`` test fixture.
    """
