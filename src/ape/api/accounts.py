from pathlib import Path
from typing import TYPE_CHECKING, Callable, Iterator, List, Optional, Type, Union

import click

from ape.exceptions import AccountsError, AliasAlreadyInUseError, SignatureError, TransactionError
from ape.logging import logger
from ape.types import AddressType, MessageSignature, SignableMessage, TransactionSignature
from ape.utils import abstractdataclass, abstractmethod, cached_property

from .address import AddressAPI
from .providers import ReceiptAPI, TransactionAPI, TransactionType

if TYPE_CHECKING:
    from ape.contracts import ContractContainer, ContractInstance
    from ape.managers.config import ConfigManager


# NOTE: AddressAPI is a dataclass already
class AccountAPI(AddressAPI):
    """
    An API class representing an account.
    """

    container: "AccountContainerAPI"

    def __dir__(self) -> List[str]:
        """
        Display methods to IPython on ``a.[TAB]`` tab completion.

        Returns:
            List[str]: Method names that IPython uses for tab completion.
        """
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
        A shortened-name for quicker access to the account.
        """
        return None

    @abstractmethod
    def sign_message(self, msg: SignableMessage) -> Optional[MessageSignature]:
        """
        Sign a message.

        Args:
          msg (:class:`~ape.types.signatures.SignableMessage`): The message to sign.
            See these
            `docs <https://eth-account.readthedocs.io/en/stable/eth_account.html#eth_account.messages.SignableMessage>`__  # noqa: E501
            for more type information on this type.

        Returns:
          :class:`~ape.types.signatures.MessageSignature` (optional): The signed message.
        """

    @abstractmethod
    def sign_transaction(self, txn: TransactionAPI) -> Optional[TransactionSignature]:
        """
        Sign a transaction.

        Args:
          txn (:class:`~ape.api.providers.TransactionAPI`): The transaction to sign.

        Returns:
          :class:`~ape.types.signatures.TransactionSignature` (optional): The signed transaction.
        """

    def call(self, txn: TransactionAPI, send_everything: bool = False) -> ReceiptAPI:
        """
        Make a transaction call.

        Raises:
            :class:`~ape.exceptions.AccountsError`: When the nonce is invalid or the sender does
              not have enough funds.
            :class:`~ape.exceptions.TransactionError`: When the required confirmations are negative.
            :class:`~ape.exceptions.SignatureError`: When the user does not sign the transaction.

        Args:
            txn (:class:`~ape.api.providers.TransactionAPI`): The transaction to submit in a call.
            send_everything (bool): ``True`` will send the value difference from balance and fee.

        Returns:
            :class:`~ape.api.providers.ReceiptAPI`
        """
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

        if txn.required_confirmations is None:
            txn.required_confirmations = self.provider.network.required_confirmations
        elif not isinstance(txn.required_confirmations, int) or txn.required_confirmations < 0:
            raise TransactionError(message="'required_confirmations' must be a positive integer.")

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
        """
        Send funds to an account.

        Args:
            account (str): The account to send funds to.
            value (str): The amount to send.
            data (str): Extra data to include in the transaction.

        Returns:
            :class:`~ape.api.providers.ReceiptAPI`
        """

        txn = self.provider.network.ecosystem.create_transaction(
            sender=self.address, receiver=self._convert(account, AddressType), **kwargs
        )

        if data:
            txn.data = self._convert(data, bytes)

        if value:
            txn.value = self._convert(value, int)

        return self.call(txn, send_everything=value is None)

    def deploy(self, contract: "ContractContainer", *args, **kwargs) -> "ContractInstance":
        """
        Create a smart contract on the blockchain. The smart contract must compile before
        deploying and a provider must be active.

        Args:
            contract (:class:`~ape.contracts.ContractContainer`):
                The type of contract to deploy.

        Returns:
            :class:`~ape.contracts.ContractInstance`: An instance of the deployed contract.
        """

        txn = contract(*args, **kwargs)
        txn.sender = self.address
        receipt = self.call(txn)

        if not receipt.contract_address:
            raise AccountsError(f"'{receipt.txn_hash}' did not create a contract.")

        address = click.style(receipt.contract_address, bold=True)
        contract_name = contract.contract_type.name or "<Unnamed Contract>"
        logger.success(f"Contract '{contract_name}' deployed to: {address}")

        from ape import _converters
        from ape.contracts import ContractInstance

        return ContractInstance(  # type: ignore
            _provider=self.provider,
            _converter=_converters,
            _address=receipt.contract_address,
            _contract_type=contract.contract_type,
        )


@abstractdataclass
class AccountContainerAPI:
    """
    An API class representing a collection of :class:`~ape.api.accounts.AccountAPI`
    instances.
    """

    data_folder: Path
    account_type: Type[AccountAPI]
    config_manager: "ConfigManager"

    @property
    @abstractmethod
    def aliases(self) -> Iterator[str]:
        """
        Iterate over all available aliases.

        Returns:
            Iterator[str]
        """

    @abstractmethod
    def __len__(self) -> int:
        """
        Number of accounts.
        """

    @abstractmethod
    def __iter__(self) -> Iterator[AccountAPI]:
        """
        Iterate over all accounts.

        Returns:
            Iterator[:class:`~ape.api.accounts.AccountAPI`]
        """

    def __getitem__(self, address: AddressType) -> AccountAPI:
        """
        Get an account by address.

        Raises:
            IndexError: When there is no local account with the given address.

        Returns:
            :class:`~ape.api.accounts.AccountAPI`
        """
        for account in self.__iter__():
            if account.address == address:
                return account

        raise IndexError(f"No local account {address}.")

    def append(self, account: AccountAPI):
        """
        Add an account to the container.

        Raises:
            :class:`~ape.exceptions.AccountsError`: When the account is already in the container.

        Args:
            account (:class:`~ape.api.accounts.AccountAPI`): The account to add.
        """
        self._verify_account_type(account)

        if account.address in self:
            raise AccountsError(f"Account '{account.address}' already in container.")

        self._verify_unused_alias(account)

        self.__setitem__(account.address, account)

    def __setitem__(self, address: AddressType, account: AccountAPI):
        raise NotImplementedError("Must define this method to use `container.append(acct)`.")

    def remove(self, account: AccountAPI):
        """
        Delete an account.

        Raises:
            :class:`~ape.exceptions.AccountsError`: When the account is not known to ``ape``.

        Args:
            account (:class:`~ape.accounts.AccountAPI`): The account to remove.
        """
        self._verify_account_type(account)

        if account.address not in self:
            raise AccountsError(f"Account '{account.address}' not known.")

        self.__delitem__(account.address)

    def __delitem__(self, address: AddressType):
        """
        Delete an account.

        Raises:
            NotImplementError: When not overridden within a plugin.

        Args:
            address (address :class:`~ape.types.AddressType`):
                        The address of the account to delete.

        """
        raise NotImplementedError("Must define this method to use `container.remove(acct)`.")

    def __contains__(self, address: AddressType) -> bool:
        """
        Check if the address is an existing account in ``ape``.

        Raises:
            IndexError: When the given account address is not in this container.

        Args:
            address (:class:`~ape.types.AddressType`): An account address.

        Returns:
            bool: ``True`` if ``ape`` manages the account with the given address.
        """
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
    Test account containers for ``ape test`` (such containers that generate accounts using
    :class:`~ape.utils.GeneratedDevAccounts`) should implement this API instead of
    ``AccountContainerAPI`` directly. This is how they show up in the ``accounts`` test fixture.
    """


class TestAccountAPI(AccountAPI):
    """
    Test accounts for ``ape test`` (such accounts that use
    :class:`~ape.utils.GeneratedDevAccounts`) should implement this API
    instead of ``AccountAPI`` directly. This is how they show up in the ``accounts`` test fixture.
    """
