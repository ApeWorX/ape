import os
from abc import abstractmethod
from collections.abc import Iterator
from functools import cached_property
from pathlib import Path
from typing import TYPE_CHECKING, Any, Optional, Union

import click
from eip712.messages import EIP712Message
from eip712.messages import SignableMessage as EIP712SignableMessage
from eth_account import Account
from eth_account.messages import encode_defunct
from eth_pydantic_types import HexBytes
from eth_utils import to_hex
from ethpm_types import ContractType

from ape.api.address import BaseAddress
from ape.api.transactions import ReceiptAPI, TransactionAPI
from ape.exceptions import (
    AccountsError,
    AliasAlreadyInUseError,
    MethodNonPayableError,
    MissingDeploymentBytecodeError,
    SignatureError,
    TransactionError,
)
from ape.logging import logger
from ape.types.address import AddressType
from ape.types.signatures import MessageSignature, SignableMessage
from ape.utils.basemodel import BaseInterfaceModel
from ape.utils.misc import raises_not_implemented

if TYPE_CHECKING:
    from ape.contracts import ContractContainer, ContractInstance


class AccountAPI(BaseInterfaceModel, BaseAddress):
    """
    An API class representing an account.
    """

    def __dir__(self) -> list[str]:
        """
        Display methods to IPython on ``a.[TAB]`` tab completion.

        Returns:
            list[str]: Method names that IPython uses for tab completion.
        """
        base_value_excludes = ("code", "codesize", "is_contract")  # Not needed for accounts
        base_values = [v for v in self._base_dir_values if v not in base_value_excludes]
        return base_values + [
            self.__class__.alias.fget.__name__,  # type: ignore[attr-defined]
            self.__class__.call.__name__,
            self.__class__.deploy.__name__,
            self.__class__.prepare_transaction.__name__,
            self.__class__.sign_message.__name__,
            self.__class__.sign_transaction.__name__,
            self.__class__.transfer.__name__,
        ]

    @property
    def alias(self) -> Optional[str]:
        """
        A shortened-name for quicker access to the account.
        """
        return None

    def sign_raw_msghash(self, msghash: HexBytes) -> Optional[MessageSignature]:
        """
        Sign a raw message hash.

        Args:
          msghash (:class:`~eth_pydantic_types.HexBytes`):
            The message hash to sign. Plugins may or may not support this operation.
            Default implementation is to raise ``NotImplementedError``.

        Returns:
          :class:`~ape.types.signatures.MessageSignature` (optional):
            The signature corresponding to the message.
        """
        raise NotImplementedError(
            f"Raw message signing is not supported by '{self.__class__.__name__}'"
        )

    @abstractmethod
    def sign_message(self, msg: Any, **signer_options) -> Optional[MessageSignature]:
        """
        Sign a message.

        Args:
          msg (Any): The message to sign. Account plugins can handle various types of messages.
            For example, :class:`~ape_accounts.accounts.KeyfileAccount` can handle
            :class:`~ape.types.signatures.SignableMessage`, str, int, and bytes.
            See these
            `docs <https://eth-account.readthedocs.io/en/stable/eth_account.html#eth_account.messages.SignableMessage>`__  # noqa: E501
            for more type information on the :class:`~ape.types.signatures.SignableMessage` type.
          **signer_options: Additional kwargs given to the signer to modify the signing operation.

        Returns:
          :class:`~ape.types.signatures.MessageSignature` (optional): The signature corresponding to the message.
        """

    @abstractmethod
    def sign_transaction(self, txn: TransactionAPI, **signer_options) -> Optional[TransactionAPI]:
        """
        Sign a transaction.

        Args:
          txn (:class:`~ape.api.transactions.TransactionAPI`): The transaction to sign.
          **signer_options: Additional kwargs given to the signer to modify the signing operation.

        Returns:
          :class:`~ape.api.transactions.TransactionAPI` (optional): A signed transaction.
            The ``TransactionAPI`` returned by this method may not correspond to ``txn`` given as
            input, however returning a properly-formatted transaction here is meant to be executed.
            Returns ``None`` if the account does not have a transaction it wishes to execute.

        """

    def call(
        self,
        txn: TransactionAPI,
        send_everything: bool = False,
        private: bool = False,
        **signer_options,
    ) -> ReceiptAPI:
        """
        Make a transaction call.

        Raises:
            :class:`~ape.exceptions.AccountsError`: When the nonce is invalid or the sender does
              not have enough funds.
            :class:`~ape.exceptions.TransactionError`: When the required confirmations are negative.
            :class:`~ape.exceptions.SignatureError`: When the user does not sign the transaction.
            :class:`~ape.exceptions.APINotImplementedError`: When setting ``private=True`` and using
              a provider that does not support private transactions.

        Args:
            txn (:class:`~ape.api.transactions.TransactionAPI`): An invoke-transaction.
            send_everything (bool): ``True`` will send the difference from balance and fee.
              Defaults to ``False``.
            private (bool): ``True`` will use the
              :meth:`~ape.api.providers.ProviderAPI.send_private_transaction` method.
            **signer_options: Additional kwargs given to the signer to modify the signing operation.

        Returns:
            :class:`~ape.api.transactions.ReceiptAPI`
        """

        txn = self.prepare_transaction(txn)
        max_fee = txn.max_fee
        gas_limit = txn.gas_limit

        if not isinstance(gas_limit, int):
            raise TransactionError("Transaction not prepared.")

        # The conditions below should never reached but are here for mypy's sake.
        # The `max_fee` was either set manually or from `prepare_transaction()`.
        # The `gas_limit` was either set manually or from `prepare_transaction()`.
        if max_fee is None:
            raise TransactionError("`max_fee` failed to get set in transaction preparation.")
        elif gas_limit is None:
            raise TransactionError("`gas_limit` failed to get set in transaction preparation.")

        total_fees = max_fee * gas_limit

        # Send the whole balance.
        if send_everything:
            amount_to_send = self.balance - total_fees
            if amount_to_send <= 0:
                raise AccountsError(
                    f"Sender does not have enough to cover transaction value and gas: "
                    f"{total_fees}"
                )
            else:
                txn.value = amount_to_send

        signed_txn = self.sign_transaction(txn, **signer_options)
        if not signed_txn:
            raise SignatureError("The transaction was not signed.")

        if not txn.sender:
            txn.sender = self.address

        return (
            self.provider.send_private_transaction(signed_txn)
            if private
            else self.provider.send_transaction(signed_txn)
        )

    def transfer(
        self,
        account: Union[str, AddressType, BaseAddress],
        value: Optional[Union[str, int]] = None,
        data: Optional[Union[bytes, str]] = None,
        private: bool = False,
        **kwargs,
    ) -> ReceiptAPI:
        """
        Send funds to an account.

        Raises:
            :class:`~ape.exceptions.APINotImplementedError`: When setting ``private=True``
              and using a provider that does not support private transactions.

        Args:
            account (Union[str, AddressType, BaseAddress]): The receiver of the funds.
            value (Optional[Union[str, int]]): The amount to send.
            data (Optional[Union[bytes, str]]): Extra data to include in the transaction.
            private (bool): ``True`` asks the provider to make the transaction
              private. For example, EVM providers typically use the RPC
              ``eth_sendPrivateTransaction`` to achieve this. Local providers may ignore
              this value.
            **kwargs: Additional transaction kwargs passed to
              :meth:`~ape.api.networks.EcosystemAPI.create_transaction`, such as ``gas``
              ``max_fee``, or ``max_priority_fee``. For a list of available transaction
              kwargs, see :class:`~ape.api.transactions.TransactionAPI`.

        Returns:
            :class:`~ape.api.transactions.ReceiptAPI`
        """

        receiver = self.conversion_manager.convert(account, AddressType)
        txn = self.provider.network.ecosystem.create_transaction(
            sender=self.address, receiver=receiver, **kwargs
        )

        if data:
            txn.data = self.conversion_manager.convert(data, bytes)

        if value is None and not kwargs.get("send_everything"):
            raise AccountsError("Must provide 'VALUE' or use 'send_everything=True'")

        elif value is not None and kwargs.get("send_everything"):
            raise AccountsError("Cannot use 'send_everything=True' with 'VALUE'.")

        elif value is not None:
            txn.value = self.conversion_manager.convert(value, int)
            if txn.value < 0:
                raise AccountsError("Value cannot be negative.")

        return self.call(txn, private=private, **kwargs)

    def deploy(
        self, contract: "ContractContainer", *args, publish: bool = False, **kwargs
    ) -> "ContractInstance":
        """
        Create a smart contract on the blockchain. The smart contract must compile before
        deploying and a provider must be active.

        Args:
            contract (:class:`~ape.contracts.base.ContractContainer`): The type of contract to
              deploy.
            publish (bool): Set to ``True`` to attempt explorer contract verification.
              Defaults to ``False``.

        Returns:
            :class:`~ape.contracts.ContractInstance`: An instance of the deployed contract.
        """
        from ape.contracts import ContractContainer

        if isinstance(contract, ContractType):
            # Hack to allow deploying ContractTypes w/o being
            # wrapped in a container first.
            contract = ContractContainer(contract)

        # NOTE: It is important to type check here to prevent cases where user
        #    may accidentally pass in a ContractInstance, which has a very
        #    different implementation for __call__ than ContractContainer.
        elif not isinstance(contract, ContractContainer):
            raise TypeError(
                "contract argument must be a ContractContainer type, "
                "such as 'project.MyContract' where 'MyContract' is the name of "
                "a contract in your project."
            )

        bytecode = contract.contract_type.deployment_bytecode
        if not bytecode or bytecode.bytecode in (None, "", "0x"):
            raise MissingDeploymentBytecodeError(contract.contract_type)

        txn = contract(*args, **kwargs)
        if kwargs.get("value") and not contract.contract_type.constructor.is_payable:
            raise MethodNonPayableError("Sending funds to a non-payable constructor.")

        txn.sender = self.address
        receipt = contract._cache_wrap(lambda: self.call(txn, **kwargs))
        if not (address := receipt.contract_address):
            raise AccountsError(f"'{receipt.txn_hash}' did not create a contract.")

        contract_type = contract.contract_type
        styled_address = click.style(receipt.contract_address, bold=True)
        contract_name = contract_type.name or "<Unnamed Contract>"
        logger.success(f"Contract '{contract_name}' deployed to: {styled_address}")
        instance = self.chain_manager.contracts.instance_from_receipt(receipt, contract_type)
        self.chain_manager.contracts.cache_deployment(instance)

        if publish:
            self.local_project.deployments.track(instance)
            self.provider.network.publish_contract(address)

        instance.base_path = contract.base_path or self.local_project.path
        return instance

    def declare(self, contract: "ContractContainer", *args, **kwargs) -> ReceiptAPI:
        """
        Deploy the "blueprint" of a contract type. For EVM providers, this likely means
        using `EIP-5202 <https://eips.ethereum.org/EIPS/eip-5202>`__, which is implemented
        in the core ``ape-ethereum`` plugin.

        Args:
            contract (:class:`~ape.contracts.base.ContractContainer`): The contract container
              to declare.

        Returns:
            :class:`~ape.api.transactions.ReceiptAPI`: The receipt of the declare transaction.
        """

        transaction = self.provider.network.ecosystem.encode_contract_blueprint(
            contract.contract_type, *args, **kwargs
        )
        receipt = self.call(transaction)
        if receipt.contract_address:
            self.chain_manager.contracts.cache_blueprint(
                receipt.contract_address, contract.contract_type
            )
        else:
            logger.debug("Failed to cache contract declaration: missing contract address.")

        return receipt

    def check_signature(
        self,
        data: Union[SignableMessage, TransactionAPI, str, EIP712Message, int, bytes],
        signature: Optional[MessageSignature] = None,  # TransactionAPI doesn't need it
        recover_using_eip191: bool = True,
    ) -> bool:
        """
        Verify a message or transaction was signed by this account.

        Args:
            data (Union[:class:`~ape.types.signatures.SignableMessage`, :class:`~ape.api.transactions.TransactionAPI`]):  # noqa: E501
              The message or transaction to verify.
            signature (Optional[:class:`~ape.types.signatures.MessageSignature`]):
              The signature to check. Defaults to ``None`` and is not needed when the first
              argument is a transaction class.
            recover_using_eip191 (bool):
              Perform recovery using EIP-191 signed message check. If set False, then will attempt
              recovery as raw hash. `data`` must be a 32 byte hash if this is set False.
              Defaults to ``True``.

        Returns:
            bool: ``True`` if the data was signed by this account. ``False`` otherwise.
        """
        if isinstance(data, str):
            data = encode_defunct(text=data)
        elif isinstance(data, int):
            data = encode_defunct(hexstr=to_hex(data))
        elif isinstance(data, bytes) and (len(data) != 32 or recover_using_eip191):
            data = encode_defunct(data)
        elif isinstance(data, EIP712Message):
            data = data.signable_message
        if isinstance(data, (SignableMessage, EIP712SignableMessage)):
            if signature:
                return self.address == Account.recover_message(data, vrs=signature)

            else:
                raise AccountsError(
                    "Parameter 'signature' required when verifying a 'SignableMessage'."
                )

        elif isinstance(data, TransactionAPI):
            return self.address == Account.recover_transaction(data.serialize_transaction())

        elif isinstance(data, bytes) and len(data) == 32 and not recover_using_eip191:
            return self.address == Account._recover_hash(data, vrs=signature)

        else:
            raise AccountsError(f"Unsupported message type: {type(data)}.")

    def prepare_transaction(self, txn: TransactionAPI) -> TransactionAPI:
        """
        Set default values on a transaction.

        Raises:
            :class:`~ape.exceptions.AccountsError`: When the account cannot afford the transaction
              or the nonce is invalid.
            :class:`~ape.exceptions.TransactionError`: When given negative required confirmations.

        Args:
            txn (:class:`~ape.api.transactions.TransactionAPI`): The transaction to prepare.

        Returns:
            :class:`~ape.api.transactions.TransactionAPI`
        """

        # NOTE: Allow overriding nonce, assume user understand what this does
        if txn.nonce is None:
            txn.nonce = self.nonce
        elif txn.nonce < self.nonce:
            raise AccountsError("Invalid nonce, will not publish.")

        txn = self.provider.prepare_transaction(txn)

        if (
            txn.sender not in self.account_manager.test_accounts._impersonated_accounts
            and txn.total_transfer_value > self.balance
        ):
            raise AccountsError(
                f"Transfer value meets or exceeds account balance "
                f"for account '{self.address}' on chain '{self.provider.chain_id}' "
                f"using provider '{self.provider.name}'.\n"
                "Are you using the correct account / chain / provider combination?\n"
                f"(transfer_value={txn.total_transfer_value}, balance={self.balance})."
            )

        return txn


class AccountContainerAPI(BaseInterfaceModel):
    """
    An API class representing a collection of :class:`~ape.api.accounts.AccountAPI`
    instances.
    """

    name: str
    """
    The name of the account container.
    For example, the ``ape-ledger`` plugin
    uses ``"ledger"`` as its name.
    """

    account_type: type[AccountAPI]
    """
    The type of account in this container.
    See :class:`~ape.api.accounts.AccountAPI`.
    """

    @property
    @abstractmethod
    def aliases(self) -> Iterator[str]:
        """
        All available aliases.

        Returns:
            Iterator[str]
        """

    @property
    @abstractmethod
    def accounts(self) -> Iterator[AccountAPI]:
        """
        All accounts.

        Returns:
            Iterator[:class:`~ape.api.accounts.AccountAPI`]
        """

    @cached_property
    def data_folder(self) -> Path:
        """
        The path to the account data files.
        Defaults to ``$HOME/.ape/<plugin_name>`` unless overridden.
        """
        path = self.config_manager.DATA_FOLDER / self.name
        path.mkdir(parents=True, exist_ok=True)
        return path

    @abstractmethod
    def __len__(self) -> int:
        """
        Number of accounts.
        """

    def __getitem__(self, address: AddressType) -> AccountAPI:
        """
        Get an account by address.

        Args:
            address (:class:`~ape.types.address.AddressType`): The address to get. The type is an alias to
              `ChecksumAddress <https://eth-typing.readthedocs.io/en/latest/types.html#checksumaddress>`__.  # noqa: E501

        Raises:
            KeyError: When there is no local account with the given address.

        Returns:
            :class:`~ape.api.accounts.AccountAPI`
        """
        for account in self.accounts:
            if account.address == address:
                return account

        raise KeyError(f"No local account {address}.")

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
            address (:class:`~ape.types.address.AddressType`): The address of the account to delete.
        """
        raise NotImplementedError("Must define this method to use `container.remove(acct)`.")

    def __contains__(self, address: AddressType) -> bool:
        """
        Check if the address is an existing account in ``ape``.

        Raises:
            IndexError: When the given account address is not in this container.

        Args:
            address (:class:`~ape.types.address.AddressType`): An account address.

        Returns:
            bool: ``True`` if ``ape`` manages the account with the given address.
        """
        try:
            self.__getitem__(address)
            return True

        except (IndexError, KeyError, AttributeError):
            return False

    def _verify_account_type(self, account):
        if not isinstance(account, self.account_type):
            container_type_name = getattr(type(account), "__name__", "<CustomContainerType>")
            account_type_name = getattr(self.account_type, "__name__", "<UnknownAccount>")
            message = (
                f"Container '{container_type_name}' is an incorrect "
                f"type for container '{account_type_name}'."
            )

            raise AccountsError(message)

    def _verify_unused_alias(self, account):
        if account.alias and account.alias in self.aliases:
            raise AliasAlreadyInUseError(account.alias)


class TestAccountContainerAPI(AccountContainerAPI):
    """
    Test account containers for ``ape test`` (such containers that generate accounts using
    :class:`~ape.utils.GeneratedDevAccounts`) should implement this API instead of
    ``AccountContainerAPI`` directly. Then, they show up in the ``accounts`` test fixture.
    """

    @cached_property
    def data_folder(self) -> Path:
        """
        **NOTE**: Test account containers do not touch
        persistent data. By default and unless overridden,
        this property returns the path to ``/dev/null`` and
        it is not used for anything.
        """
        return Path("/dev/null" if os.name == "posix" else "NUL")

    @raises_not_implemented
    def get_test_account(self, index: int) -> "TestAccountAPI":  # type: ignore[empty-body]
        """
        Get the test account at the given index.

        Args:
            index (int): The index of the test account.

        Returns:
            :class:`~ape.api.accounts.TestAccountAPI`
        """

    @abstractmethod
    def generate_account(self, index: Optional[int] = None) -> "TestAccountAPI":
        """
        Generate a new test account.
        """

    def reset(self):
        """
        Reset the account container to an original state.
        """


class TestAccountAPI(AccountAPI):
    """
    Test accounts for ``ape test`` (such accounts that use
    :class:`~ape.utils.GeneratedDevAccounts`) should implement this API
    instead of ``AccountAPI`` directly. Then, they show up in the ``accounts`` test fixture.
    """


class ImpersonatedAccount(AccountAPI):
    """
    An account to use that does not require signing.
    """

    raw_address: AddressType
    """
    The field-address of the account.
    """

    @property
    def address(self) -> AddressType:
        return self.raw_address

    def sign_message(self, msg: Any, **signer_options) -> Optional[MessageSignature]:
        raise NotImplementedError("This account cannot sign messages")

    def sign_transaction(self, txn: TransactionAPI, **signer_options) -> Optional[TransactionAPI]:
        # Returns input transaction unsigned (since it doesn't have access to the key)
        return txn

    def call(
        self, txn: TransactionAPI, send_everything: bool = False, private: bool = False, **kwargs
    ) -> ReceiptAPI:
        txn = self.prepare_transaction(txn)
        txn.sender = txn.sender or self.raw_address

        return (
            self.provider.send_private_transaction(txn)
            if private
            else self.provider.send_transaction(txn)
        )
