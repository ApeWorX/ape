from pathlib import Path
from typing import TYPE_CHECKING, Callable, Iterator, List, Optional, Type, Union

import click
from eth_account import Account

from ape.exceptions import AccountsError, AliasAlreadyInUseError, SignatureError, TransactionError
from ape.logging import logger
from ape.types import AddressType, MessageSignature, SignableMessage, TransactionSignature
from ape.types.signatures import _Signature
from ape.utils import BaseInterfaceModel, abstractmethod, cached_property

from .address import BaseAddress
from .transactions import ReceiptAPI, TransactionAPI

if TYPE_CHECKING:
    from ape.contracts import ContractContainer, ContractInstance


class AccountAPI(BaseInterfaceModel, BaseAddress):
    """
    An API class representing an account.
    """

    def __dir__(self) -> List[str]:
        """
        Display methods to IPython on ``a.[TAB]`` tab completion.

        Returns:
            List[str]: Method names that IPython uses for tab completion.
        """
        return list(super(BaseAddress, self).__dir__()) + [
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

        txn = self.prepare_transaction(txn)

        if send_everything:
            if txn.max_fee is None:
                raise TransactionError(message="Max fee must not be None.")

            txn.value = self.balance - txn.max_fee

        txn.signature = self.sign_transaction(txn)
        if not txn.signature:
            raise SignatureError("The transaction was not signed.")

        return self.provider.send_transaction(txn)

    @cached_property
    def _convert(self) -> Callable:
        return self.conversion_manager.convert

    def transfer(
        self,
        account: Union[str, AddressType, BaseAddress],
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

        return self.create_contract(
            address=receipt.contract_address,  # type: ignore
            contract_type=contract.contract_type,
        )

    def check_signature(
        self,
        data: Union[SignableMessage, TransactionAPI],
        signature: Optional[_Signature] = None,  # TransactionAPI doesn't need it
    ) -> bool:
        """
        Verify a message or transaction was signed by this account.

        Args:
            data (Union[:class:`~ape.types.signatures.SignableMessage`, :class:`~ape.api.providers.TransactionAPI`]):  # noqa: E501
              The message or transaction to verify.
            signature (Optional[``_Signature``]): The :class:`~ape.types.signatures.MessageSignature` or the
              :class:`~ape.types.signatures.TransactionSignature`.

        Returns:
            bool: ``True`` if the data was signed by this account. ``False`` otherwise.
        """
        if isinstance(data, SignableMessage):
            if signature:
                return self.address == Account.recover_message(data, vrs=signature)
            else:
                raise ValueError(
                    "Parameter 'signature' required when verifying a 'SignableMessage'."
                )
        elif isinstance(data, TransactionAPI):
            return self.address == Account.recover_transaction(data.serialize_transaction())
        else:
            raise ValueError(f"Unsupported Message type: {type(data)}.")

    def prepare_transaction(self, txn: TransactionAPI) -> TransactionAPI:
        """
        Set default values on a transaction.

        Raises:
            :class:`~ape.exceptions.AccountsError`: When the account cannot afford the transaction
              or the nonce is invalid.
            :class:`~ape.exceptions.TransactionError`: When given negative required confirmations.

        Args:
            txn (:class:`~ape.api.providers.TransactionAPI`): The transaction to prepare.

        Returns:
            :class:`~ape.api.providers.TransactionAPI`
        """

        # NOTE: Allow overriding nonce, assume user understand what this does
        if txn.nonce is None:
            txn.nonce = self.nonce
        elif txn.nonce < self.nonce:
            raise AccountsError("Invalid nonce, will not publish.")

        txn = self.provider.prepare_transaction(txn)

        if txn.total_transfer_value > self.balance:
            raise AccountsError(
                "Transfer value meets or exceeds account balance.\n"
                "Are you using the correct provider/account combination?\n"
                f"(transfer_value={txn.total_transfer_value}, balance={self.balance})."
            )

        return txn


class AccountContainerAPI(BaseInterfaceModel):
    """
    An API class representing a collection of :class:`~ape.api.accounts.AccountAPI`
    instances.
    """

    data_folder: Path
    account_type: Type[AccountAPI]

    @property
    @abstractmethod
    def aliases(self) -> Iterator[str]:
        """
        Iterate over all available aliases.

        Returns:
            Iterator[str]
        """

    @property
    @abstractmethod
    def accounts(self) -> Iterator[AccountAPI]:
        """
        Iterate over all accounts.

        Returns:
            Iterator[:class:`~ape.api.accounts.AccountAPI`]
        """

    @abstractmethod
    def __len__(self) -> int:
        """
        Number of accounts.
        """

    def __getitem__(self, address: AddressType) -> AccountAPI:
        """
        Get an account by address.

        Args:
            address (``AddressType``): The address to get. The type is an alias to
              `ChecksumAddress <https://eth-typing.readthedocs.io/en/latest/types.html#checksumaddress>`__.  # noqa: E501

        Raises:
            IndexError: When there is no local account with the given address.

        Returns:
            :class:`~ape.api.accounts.AccountAPI`
        """
        for account in self.accounts:
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
            address (``AddressType``): The address of the account to delete.
        """
        raise NotImplementedError("Must define this method to use `container.remove(acct)`.")

    def __contains__(self, address: AddressType) -> bool:
        """
        Check if the address is an existing account in ``ape``.

        Raises:
            IndexError: When the given account address is not in this container.

        Args:
            address (``AddressType``): An account address.

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


class ImpersonatedAccount(AccountAPI):
    """
    An account to use that does not require signing.
    """

    raw_address: AddressType

    @property
    def address(self) -> AddressType:
        return self.raw_address

    def sign_message(self, msg: SignableMessage) -> Optional[MessageSignature]:
        raise NotImplementedError("This account cannot sign messages")

    def sign_transaction(self, txn: TransactionAPI) -> Optional[TransactionSignature]:
        return None

    def call(self, txn: TransactionAPI, send_everything: bool = False) -> ReceiptAPI:
        txn = self.prepare_transaction(txn)
        return self.provider.send_transaction(txn)
