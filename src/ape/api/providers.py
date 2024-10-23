import atexit
import ctypes
import datetime
import logging
import platform
import shutil
import sys
import time
import warnings
from abc import abstractmethod
from collections.abc import Iterable, Iterator
from functools import cached_property
from logging import FileHandler, Formatter, Logger, getLogger
from pathlib import Path
from signal import SIGINT, SIGTERM, signal
from subprocess import DEVNULL, PIPE, Popen
from typing import TYPE_CHECKING, Any, Optional, Union, cast

from eth_pydantic_types import HexBytes
from ethpm_types.abi import EventABI
from pydantic import Field, computed_field, field_serializer, model_validator

from ape.api.config import PluginConfig
from ape.api.networks import NetworkAPI
from ape.api.query import BlockTransactionQuery
from ape.api.trace import TraceAPI
from ape.api.transactions import ReceiptAPI, TransactionAPI
from ape.exceptions import (
    APINotImplementedError,
    ProviderError,
    QueryEngineError,
    RPCTimeoutError,
    SubprocessError,
    SubprocessTimeoutError,
    VirtualMachineError,
)
from ape.logging import LogLevel, logger
from ape.types.address import AddressType
from ape.types.basic import HexInt
from ape.types.events import ContractLog, LogFilter
from ape.types.vm import BlockID, ContractCode, SnapshotID
from ape.utils.basemodel import BaseInterfaceModel
from ape.utils.misc import (
    EMPTY_BYTES32,
    _create_raises_not_implemented_error,
    log_instead_of_fail,
    raises_not_implemented,
    to_int,
)
from ape.utils.process import JoinableQueue, spawn
from ape.utils.rpc import RPCHeaders

if TYPE_CHECKING:
    from ape.api.accounts import TestAccountAPI


class BlockAPI(BaseInterfaceModel):
    """
    An abstract class representing a block and its attributes.
    """

    # NOTE: All fields in this class (and it's subclasses) should not be `Optional`
    #       except the edge cases noted below

    num_transactions: HexInt = 0
    """
    The number of transactions in the block.
    """

    hash: Optional[Any] = None  # NOTE: pending block does not have a hash
    """
    The block hash identifier.
    """

    number: Optional[HexInt] = None  # NOTE: pending block does not have a number
    """
    The block number identifier.
    """

    parent_hash: Any = Field(
        default=EMPTY_BYTES32, alias="parentHash"
    )  # NOTE: genesis block has no parent hash
    """
    The preceding block's hash.
    """

    timestamp: HexInt
    """
    The timestamp the block was produced.
    NOTE: The pending block uses the current timestamp.
    """

    _size: Optional[HexInt] = None

    @log_instead_of_fail(default="<BlockAPI>")
    def __repr__(self) -> str:
        return super().__repr__()

    @property
    def datetime(self) -> datetime.datetime:
        """
        The block timestamp as a datetime object.
        """
        return datetime.datetime.fromtimestamp(self.timestamp, tz=datetime.timezone.utc)

    @model_validator(mode="before")
    @classmethod
    def convert_parent_hash(cls, data):
        parent_hash = data.get("parent_hash", data.get("parentHash")) or EMPTY_BYTES32
        data["parentHash"] = parent_hash
        return data

    @model_validator(mode="wrap")
    @classmethod
    def validate_size(cls, values, handler):
        """
        A validator for handling non-computed size.
        Saves it to a private member on this class and
        gets returned in computed field "size".
        """
        if isinstance(values, BlockAPI):
            size = values.size

        else:
            if not hasattr(values, "pop"):
                # Handle weird AttributeDict missing pop method.
                # https://github.com/ethereum/web3.py/issues/3326
                values = {**values}

            size = values.pop("size", None)

        model = handler(values)
        if size is not None:
            model._size = to_int(size)

        return model

    @field_serializer("size")
    def serialize_size(self, value):
        return to_int(value)

    @computed_field()  # type: ignore[misc]
    @cached_property
    def transactions(self) -> list[TransactionAPI]:
        """
        All transactions in a block.
        """
        try:
            query = BlockTransactionQuery(columns=["*"], block_id=self.hash)
            return cast(list[TransactionAPI], list(self.query_manager.query(query)))
        except QueryEngineError as err:
            # NOTE: Re-raising a better error here because was confusing
            #  when doing anything with fields, and this would fail.
            raise ProviderError(f"Unable to find block transactions: {err}") from err

    @computed_field()  # type: ignore[misc]
    @cached_property
    def size(self) -> HexInt:
        """
        The size of the block in gas. Most of the time,
        this field is passed to the model at validation time,
        but occasionally it is missing (like in `eth_subscribe:newHeads`),
        in which case it gets calculated if and only if the user
        requests it (or during serialization of this model to disk).
        """
        if self._size is not None:
            # The size was provided with the rest of the model
            # (normal).
            return self._size

        raise APINotImplementedError()


class ProviderAPI(BaseInterfaceModel):
    """
    An abstraction of a connection to a network in an ecosystem. Example ``ProviderAPI``
    implementations include the `ape-infura <https://github.com/ApeWorX/ape-infura>`__
    plugin or the `ape-hardhat <https://github.com/ApeWorX/ape-hardhat>`__ plugin.
    """

    name: str
    """The name of the provider (should be the plugin name)."""

    network: NetworkAPI
    """A reference to the network this provider provides."""

    provider_settings: dict = {}
    """The settings for the provider, as overrides to the configuration."""

    # TODO: In 0.9, make @property that returns value from config,
    #   and use REQUEST_HEADER as plugin-defined constants.
    request_header: dict = {}
    """A header to set on HTTP/RPC requests."""

    block_page_size: int = 100
    """
    The amount of blocks to fetch in a response, as a default.
    This is particularly useful for querying logs across a block range.
    """

    concurrency: int = 4
    """
    How many parallel threads to use when fetching logs.
    """

    @property
    def data_folder(self) -> Path:
        """
        The path to the provider's data,
        e.g. ``$HOME/.api/{self.name}`` unless overridden.
        """
        return self.config_manager.DATA_FOLDER / self.name

    @property
    @abstractmethod
    def is_connected(self) -> bool:
        """
        ``True`` if currently connected to the provider. ``False`` otherwise.
        """

    @property
    def connection_str(self) -> str:
        """
        The str representing how to connect
        to the node, such as an HTTP URL
        or an IPC path.
        """
        return ""

    @abstractmethod
    def connect(self):
        """
        Connect a to a provider, such as start-up a process or create an HTTP connection.
        """

    @abstractmethod
    def disconnect(self):
        """
        Disconnect from a provider, such as tear-down a process or quit an HTTP session.
        """

    @property
    def http_uri(self) -> Optional[str]:
        """
        Return the raw HTTP/HTTPS URI to connect to this provider, if supported.
        """
        return None

    @property
    def ws_uri(self) -> Optional[str]:
        """
        Return the raw WS/WSS URI to connect to this provider, if supported.
        """
        return None

    @property
    def settings(self) -> PluginConfig:
        """
        The combination of settings from ``ape-config.yaml`` and ``.provider_settings``.
        """
        CustomConfig = self.config.__class__
        data = {**self.config.model_dump(), **self.provider_settings}
        return CustomConfig.model_validate(data)

    @property
    def connection_id(self) -> Optional[str]:
        """
        A connection ID to uniquely identify and manage multiple
        connections to providers, especially when working with multiple
        providers of the same type, like multiple Geth --dev nodes.
        """

        try:
            chain_id = self.chain_id
        except Exception:
            if chain_id := self.settings.get("chain_id"):
                pass

            else:
                # A connection is required to obtain a chain ID for this provider.
                return None

        # NOTE: If other provider settings are different, ``.update_settings()``
        #    should be called.
        return f"{self.network_choice}:{chain_id}"

    @abstractmethod
    def update_settings(self, new_settings: dict):
        """
        Change a provider's setting, such as configure a new port to run on.
        May require a reconnect.

        Args:
            new_settings (dict): The new provider settings.
        """

    @property
    @abstractmethod
    def chain_id(self) -> int:
        """
        The blockchain ID.
        See `ChainList <https://chainlist.org/>`__ for a comprehensive list of IDs.
        """

    @abstractmethod
    def get_balance(self, address: AddressType, block_id: Optional[BlockID] = None) -> int:
        """
        Get the balance of an account.

        Args:
            address (:class:`~ape.types.address.AddressType`): The address of the account.
            block_id (:class:`~ape.types.BlockID`): Optionally specify a block
              ID. Defaults to using the latest block.

        Returns:
            int: The account balance.
        """

    @abstractmethod
    def get_code(self, address: AddressType, block_id: Optional[BlockID] = None) -> ContractCode:
        """
        Get the bytes a contract.

        Args:
            address (:class:`~ape.types.address.AddressType`): The address of the contract.
            block_id (Optional[:class:`~ape.types.BlockID`]): The block ID
                  for checking a previous account nonce.

        Returns:
            :class:`~ape.types.ContractCode`: The contract bytecode.
        """

    @property
    def network_choice(self) -> str:
        """
        The connected network choice string.
        """
        if self.network.is_adhoc and self.connection_str:
            # `custom` is not a real network and is same
            # as using raw connection str
            return self.connection_str

        elif self.network.is_adhoc:
            raise ProviderError("Custom network provider missing `connection_str`.")

        return f"{self.network.choice}:{self.name}"

    @abstractmethod
    def make_request(self, rpc: str, parameters: Optional[Iterable] = None) -> Any:
        """
        Make a raw RPC request to the provider.
        Advanced featues such as tracing may utilize this to by-pass unnecessary
        class-serializations.
        """

    @raises_not_implemented
    def stream_request(  # type: ignore[empty-body]
        self, method: str, params: Iterable, iter_path: str = "result.item"
    ) -> Iterator[Any]:
        """
        Stream a request, great for large requests like events or traces.

        Args:
            method (str): The RPC method to call.
            params (Iterable): Parameters for the method.s
            iter_path (str): The response dict-path to the items.

        Returns:
            An iterator of items.
        """

    # TODO: In 0.9, delete this method.
    def get_storage_at(self, *args, **kwargs) -> HexBytes:
        warnings.warn(
            "'provider.get_storage_at()' is deprecated. Use 'provider.get_storage()'.",
            DeprecationWarning,
        )
        return self.get_storage(*args, **kwargs)

    @raises_not_implemented
    def get_storage(  # type: ignore[empty-body]
        self, address: AddressType, slot: int, block_id: Optional[BlockID] = None
    ) -> HexBytes:
        """
        Gets the raw value of a storage slot of a contract.

        Args:
            address (AddressType): The address of the contract.
            slot (int): Storage slot to read the value of.
            block_id (Optional[:class:`~ape.types.BlockID`]): The block ID
              for checking a previous storage value.

        Returns:
            HexBytes: The value of the storage slot.
        """

    @abstractmethod
    def get_nonce(self, address: AddressType, block_id: Optional[BlockID] = None) -> int:
        """
        Get the number of times an account has transacted.

        Args:
            address (AddressType): The address of the account.
            block_id (Optional[:class:`~ape.types.BlockID`]): The block ID
              for checking a previous account nonce.

        Returns:
            int
        """

    @abstractmethod
    def estimate_gas_cost(self, txn: TransactionAPI, block_id: Optional[BlockID] = None) -> int:
        """
        Estimate the cost of gas for a transaction.

        Args:
            txn (:class:`~ape.api.transactions.TransactionAPI`):
              The transaction to estimate the gas for.
            block_id (Optional[:class:`~ape.types.BlockID`]): The block ID
              to use when estimating the transaction. Useful for checking a
              past estimation cost of a transaction.

        Returns:
            int: The estimated cost of gas to execute the transaction
            reported in the fee-currency's smallest unit, e.g. Wei. If the
            provider's network has been configured with a gas limit override, it
            will be returned. If the gas limit configuration is "max" this will
            return the block maximum gas limit.
        """

    @property
    @abstractmethod
    def gas_price(self) -> int:
        """
        The price for what it costs to transact
        (pre-`EIP-1559 <https://eips.ethereum.org/EIPS/eip-1559>`__).
        """

    @property
    @abstractmethod
    def max_gas(self) -> int:
        """
        The max gas limit value you can use.
        """

    @property
    def config(self) -> PluginConfig:
        """
        The provider's configuration.
        """
        return self.config_manager.get_config(self.name)

    @property
    def priority_fee(self) -> int:
        """
        A miner tip to incentivize them to include your transaction in a block.

        Raises:
            NotImplementedError: When the provider does not implement
              `EIP-1559 <https://eips.ethereum.org/EIPS/eip-1559>`__ typed transactions.
        """
        raise APINotImplementedError("priority_fee is not implemented by this provider")

    @property
    def supports_tracing(self) -> bool:
        """
        ``True`` when the provider can provide transaction traces.
        """
        return False

    @property
    def base_fee(self) -> int:
        """
        The minimum value required to get your transaction included on the next block.
        Only providers that implement `EIP-1559 <https://eips.ethereum.org/EIPS/eip-1559>`__
        will use this property.

        Raises:
            NotImplementedError: When this provider does not implement
              `EIP-1559 <https://eips.ethereum.org/EIPS/eip-1559>`__.
        """
        raise APINotImplementedError("base_fee is not implemented by this provider")

    @abstractmethod
    def get_block(self, block_id: BlockID) -> BlockAPI:
        """
        Get a block.

        Args:
            block_id (:class:`~ape.types.BlockID`): The ID of the block to get.
                Can be ``"latest"``, ``"earliest"``, ``"pending"``, a block hash or a block number.

        Raises:
            :class:`~ape.exceptions.BlockNotFoundError`: Likely the exception raised when a block
              is not found (depends on implementation).

        Returns:
            :class:`~ape.types.BlockID`: The block for the given ID.
        """

    @abstractmethod
    def send_call(
        self,
        txn: TransactionAPI,
        block_id: Optional[BlockID] = None,
        state: Optional[dict] = None,
        **kwargs,
    ) -> HexBytes:  # Return value of function
        """
        Execute a new transaction call immediately without creating a
        transaction on the block chain.

        Args:
            txn: :class:`~ape.api.transactions.TransactionAPI`
            block_id (Optional[:class:`~ape.types.BlockID`]): The block ID
                to use to send a call at a historical point of a contract.
                Useful for checking a past estimation cost of a transaction.
            state (Optional[dict]): Modify the state of the blockchain
                prior to sending the call, for testing purposes.
            **kwargs: Provider-specific extra kwargs.

        Returns:
            str: The result of the transaction call.
        """

    @abstractmethod
    def get_receipt(self, txn_hash: str, **kwargs) -> ReceiptAPI:
        """
        Get the information about a transaction from a transaction hash.

        Args:
            txn_hash (str): The hash of the transaction to retrieve.
            kwargs: Any other kwargs that other providers might allow when fetching a receipt.

        Returns:
            :class:`~api.providers.ReceiptAPI`:
            The receipt of the transaction with the given hash.
        """

    @abstractmethod
    def get_transactions_by_block(self, block_id: BlockID) -> Iterator[TransactionAPI]:
        """
        Get the information about a set of transactions from a block.

        Args:
            block_id (:class:`~ape.types.BlockID`): The ID of the block.

        Returns:
            Iterator[:class: `~ape.api.transactions.TransactionAPI`]
        """

    @raises_not_implemented
    def get_transactions_by_account_nonce(  # type: ignore[empty-body]
        self,
        account: AddressType,
        start_nonce: int = 0,
        stop_nonce: int = -1,
    ) -> Iterator[ReceiptAPI]:
        """
        Get account history for the given account.

        Args:
            account (:class:`~ape.types.address.AddressType`): The address of the account.
            start_nonce (int): The nonce of the account to start the search with.
            stop_nonce (int): The nonce of the account to stop the search with.

        Returns:
            Iterator[:class:`~ape.api.transactions.ReceiptAPI`]
        """

    @abstractmethod
    def send_transaction(self, txn: TransactionAPI) -> ReceiptAPI:
        """
        Send a transaction to the network.

        Args:
            txn (:class:`~ape.api.transactions.TransactionAPI`): The transaction to send.

        Returns:
            :class:`~ape.api.transactions.ReceiptAPI`
        """

    @abstractmethod
    def get_contract_logs(self, log_filter: LogFilter) -> Iterator[ContractLog]:
        """
        Get logs from contracts.

        Args:
            log_filter (:class:`~ape.types.LogFilter`): A mapping of event ABIs to
              topic filters. Defaults to getting all events.

        Returns:
            Iterator[:class:`~ape.types.ContractLog`]
        """

    def send_private_transaction(self, txn: TransactionAPI, **kwargs) -> ReceiptAPI:
        """
        Send a transaction through a private mempool (if supported by the Provider).

        Raises:
            :class:`~ape.exceptions.APINotImplementedError`: If using a non-local
              network and not implemented by the provider.

        Args:
            txn (:class:`~ape.api.transactions.TransactionAPI`): The transaction
              to privately publish.
            **kwargs: Additional kwargs to be optionally handled by the provider.

        Returns:
            :class:`~ape.api.transactions.ReceiptAPI`
        """
        if self.network.is_dev:
            # Send the transaction as normal so testers can verify private=True
            # and the txn still goes through.
            logger.warning(
                f"private=True is set but connected to network '{self.network.name}' ."
                f"Using regular '{self.send_transaction.__name__}()' method (not private)."
            )
            return self.send_transaction(txn)

        # What happens normally from `raises_not_implemented()` decorator.
        raise _create_raises_not_implemented_error(self.send_private_transaction)

    @raises_not_implemented
    def snapshot(self) -> SnapshotID:  # type: ignore[empty-body]
        """
        Defined to make the ``ProviderAPI`` interchangeable with a
        :class:`~ape.api.providers.TestProviderAPI`, as in
        :class:`ape.managers.chain.ChainManager`.

        Raises:
            :class:`~ape.exceptions.APINotImplementedError`: Unless overriden.
        """

    @raises_not_implemented
    def restore(self, snapshot_id: SnapshotID):
        """
        Defined to make the ``ProviderAPI`` interchangeable with a
        :class:`~ape.api.providers.TestProviderAPI`, as in
        :class:`ape.managers.chain.ChainManager`.

        Raises:
            :class:`~ape.exceptions.APINotImplementedError`: Unless overriden.
        """

    @raises_not_implemented
    def set_timestamp(self, new_timestamp: int):
        """
        Defined to make the ``ProviderAPI`` interchangeable with a
        :class:`~ape.api.providers.TestProviderAPI`, as in
        :class:`ape.managers.chain.ChainManager`.

        Raises:
            :class:`~ape.exceptions.APINotImplementedError`: Unless overriden.
        """

    @raises_not_implemented
    def mine(self, num_blocks: int = 1):
        """
        Defined to make the ``ProviderAPI`` interchangeable with a
        :class:`~ape.api.providers.TestProviderAPI`, as in
        :class:`ape.managers.chain.ChainManager`.

        Raises:
            :class:`~ape.exceptions.APINotImplementedError`: Unless overriden.
        """

    @raises_not_implemented
    def set_balance(self, address: AddressType, amount: int):
        """
        Change the balance of an account.

        Args:
            address (AddressType): An address on the network.
            amount (int): The balance to set in the address.
        """

    @raises_not_implemented
    def get_test_account(self, index: int) -> "TestAccountAPI":  # type: ignore[empty-body]
        """
        Retrieve one of the provider-generated test accounts.

        Args:
            index (int): The index of the test account in the HD-Path.

        Returns:
            :class:`~ape.api.accounts.TestAccountAPI`
        """

    @log_instead_of_fail(default="<ProviderAPI>")
    def __repr__(self) -> str:
        return f"<{self.name.capitalize()} chain_id={self.chain_id}>"

    @raises_not_implemented
    def set_code(  # type: ignore[empty-body]
        self, address: AddressType, code: ContractCode
    ) -> bool:
        """
        Change the code of a smart contract, for development purposes.
        Test providers implement this method when they support it.

        Args:
            address (AddressType): An address on the network.
            code (:class:`~ape.types.ContractCode`): The new bytecode.
        """

    @raises_not_implemented
    def set_storage(  # type: ignore[empty-body]
        self, address: AddressType, slot: int, value: HexBytes
    ):
        """
        Sets the raw value of a storage slot of a contract.

        Args:
            address (str): The address of the contract.
            slot (int): Storage slot to write the value to.
            value: (HexBytes): The value to overwrite the raw storage slot with.
        """

    @raises_not_implemented
    def unlock_account(self, address: AddressType) -> bool:  # type: ignore[empty-body]
        """
        Ask the provider to allow an address to submit transactions without validating
        signatures. This feature is intended to be subclassed by a
        :class:`~ape.api.providers.TestProviderAPI` so that during a fork-mode test,
        a transaction can be submitted by an arbitrary account or contract without a private key.

        Raises:
            NotImplementedError: When this provider does not support unlocking an account.

        Args:
            address (:class:`~ape.types.address.AddressType`): The address to unlock.

        Returns:
            bool: ``True`` if successfully unlocked account and ``False`` otherwise.
        """

    @raises_not_implemented
    def relock_account(self, address: AddressType):
        """
        Stop impersonating an account.

        Args:
            address (:class:`~ape.types.address.AddressType`): The address to relock.
        """

    @raises_not_implemented
    def get_transaction_trace(  # type: ignore[empty-body]
        self, txn_hash: Union[HexBytes, str]
    ) -> TraceAPI:
        """
        Provide a detailed description of opcodes.

        Args:
            transaction_hash (Union[HexBytes, str]): The hash of a transaction
              to trace.

        Returns:
            :class:`~ape.api.trace.TraceAPI`: A transaction trace.
        """

    @raises_not_implemented
    def poll_blocks(  # type: ignore[empty-body]
        self,
        stop_block: Optional[int] = None,
        required_confirmations: Optional[int] = None,
        new_block_timeout: Optional[int] = None,
    ) -> Iterator[BlockAPI]:
        """
        Poll new blocks.

        **NOTE**: When a chain reorganization occurs, this method logs an error and
        yields the missed blocks, even if they were previously yielded with different
        block numbers.

        **NOTE**: This is a daemon method; it does not terminate unless an exception occurs
        or a ``stop_block`` is given.

        Args:
            stop_block (Optional[int]): Optionally set a future block number to stop at.
              Defaults to never-ending.
            required_confirmations (Optional[int]): The amount of confirmations to wait
              before yielding the block. The more confirmations, the less likely a reorg will occur.
              Defaults to the network's configured required confirmations.
            new_block_timeout (Optional[float]): The amount of time to wait for a new block before
              timing out. Defaults to 10 seconds for local networks or ``50 * block_time`` for live
              networks.

        Returns:
            Iterator[:class:`~ape.api.providers.BlockAPI`]
        """

    @raises_not_implemented
    def poll_logs(  # type: ignore[empty-body]
        self,
        stop_block: Optional[int] = None,
        address: Optional[AddressType] = None,
        topics: Optional[list[Union[str, list[str]]]] = None,
        required_confirmations: Optional[int] = None,
        new_block_timeout: Optional[int] = None,
        events: Optional[list[EventABI]] = None,
    ) -> Iterator[ContractLog]:
        """
        Poll new blocks. Optionally set a start block to include historical blocks.

        **NOTE**: This is a daemon method; it does not terminate unless an exception occurs.

        Usage example::

            for new_log in contract.MyEvent.poll_logs():
                print(f"New event log found: block_number={new_log.block_number}")

        Args:
            stop_block (Optional[int]): Optionally set a future block number to stop at.
              Defaults to never-ending.
            address (Optional[str]): The address of the contract to filter logs by.
              Defaults to all addresses.
            topics (Optional[list[Union[str, list[str]]]]): The topics to filter logs by.
              Defaults to all topics.
            required_confirmations (Optional[int]): The amount of confirmations to wait
              before yielding the block. The more confirmations, the less likely a reorg will occur.
              Defaults to the network's configured required confirmations.
            new_block_timeout (Optional[int]): The amount of time to wait for a new block before
              quitting. Defaults to 10 seconds for local networks or ``50 * block_time`` for live
              networks.
            events (Optional[list[``EventABI``]]): An optional list of events to listen on.

        Returns:
            Iterator[:class:`~ape.types.ContractLog`]
        """

    def prepare_transaction(self, txn: TransactionAPI) -> TransactionAPI:
        """
        Set default values on the transaction.

        Raises:
            :class:`~ape.exceptions.TransactionError`: When given negative required confirmations.

        Args:
            txn (:class:`~ape.api.transactions.TransactionAPI`): The transaction to prepare.

        Returns:
            :class:`~ape.api.transactions.TransactionAPI`
        """
        return txn

    def get_virtual_machine_error(self, exception: Exception, **kwargs) -> VirtualMachineError:
        """
        Get a virtual machine error from an error returned from your RPC.

        Args:
            exception (Exception): The error returned from your RPC client.

        Returns:
            :class:`~ape.exceptions.VirtualMachineError`: An error representing what
               went wrong in the call.
        """
        return VirtualMachineError(base_err=exception, **kwargs)

    def _get_request_headers(self) -> RPCHeaders:
        # Internal helper method called by NetworkManager
        headers = RPCHeaders(**self.request_header)
        # Have to do it this way to avoid "multiple-keys" error.
        configured_headers: dict = self.config.get("request_headers", {})
        for key, value in configured_headers.items():
            headers[key] = value

        return headers


class TestProviderAPI(ProviderAPI):
    """
    An API for providers that have development functionality, such as snapshotting.
    """

    @cached_property
    def test_config(self) -> PluginConfig:
        return self.config_manager.get_config("test")

    @abstractmethod
    def snapshot(self) -> SnapshotID:
        """
        Record the current state of the blockchain with intent to later
        call the method :meth:`~ape.managers.chain.ChainManager.revert`
        to go back to this point. This method is for local networks only.

        Returns:
            :class:`~ape.types.SnapshotID`: The snapshot ID.
        """

    @abstractmethod
    def restore(self, snapshot_id: SnapshotID):
        """
        Regress the current call using the given snapshot ID.
        Allows developers to go back to a previous state.

        Args:
            snapshot_id (str): The snapshot ID.
        """

    @abstractmethod
    def set_timestamp(self, new_timestamp: int):
        """
        Change the pending timestamp.

        Args:
            new_timestamp (int): The timestamp to set.

        Returns:
            int: The new timestamp.
        """

    @abstractmethod
    def mine(self, num_blocks: int = 1):
        """
        Advance by the given number of blocks.

        Args:
            num_blocks (int): The number of blocks allotted to mine. Defaults to ``1``.
        """

    @property
    @abstractmethod
    def auto_mine(self) -> bool:
        """
        Whether automine is enabled.
        """

    @auto_mine.setter
    @abstractmethod
    def auto_mine(self) -> bool:
        """
        Enable or disbale automine.
        """

    def _increment_call_func_coverage_hit_count(self, txn: TransactionAPI):
        """
        A helper method for incrementing a method call function hit count in a
        non-orthodox way. This is because Hardhat does not support call traces yet.
        """
        if (
            not txn.receiver
            or not self._test_runner
            or not self._test_runner.config_wrapper.track_coverage
        ):
            return

        if not (contract_type := self.chain_manager.contracts.get(txn.receiver)) or not (
            contract_src := self.local_project._create_contract_source(contract_type)
        ):
            return

        method_id = txn.data[:4]
        if method_id in contract_type.view_methods:
            method = contract_type.methods[method_id]
            self._test_runner.coverage_tracker.hit_function(contract_src, method)


class UpstreamProvider(ProviderAPI):
    """
    A provider that can also be set as another provider's upstream.
    """


class SubprocessProvider(ProviderAPI):
    """
    A provider that manages a process, such as for ``ganache``.
    """

    PROCESS_WAIT_TIMEOUT: int = 15
    process: Optional[Popen] = None
    is_stopping: bool = False

    stdout_queue: Optional[JoinableQueue] = None
    stderr_queue: Optional[JoinableQueue] = None

    @property
    @abstractmethod
    def process_name(self) -> str:
        """The name of the process, such as ``Hardhat node``."""

    @abstractmethod
    def build_command(self) -> list[str]:
        """
        Get the command as a list of ``str``.
        Subclasses should override and add command arguments if needed.

        Returns:
            list[str]: The command to pass to ``subprocess.Popen``.
        """

    @property
    def base_logs_path(self) -> Path:
        return self.config_manager.DATA_FOLDER / self.name / "subprocess_output"

    @property
    def stdout_logs_path(self) -> Path:
        return self.base_logs_path / "stdout.log"

    @property
    def stderr_logs_path(self) -> Path:
        return self.base_logs_path / "stderr.log"

    @cached_property
    def _stdout_logger(self) -> Logger:
        return self._get_process_output_logger("stdout", self.stdout_logs_path)

    @cached_property
    def _stderr_logger(self) -> Logger:
        return self._get_process_output_logger("stderr", self.stderr_logs_path)

    @property
    def connection_id(self) -> Optional[str]:
        cmd_id = ",".join(self.build_command())
        return f"{self.network_choice}:{cmd_id}"

    def _get_process_output_logger(self, name: str, path: Path):
        logger = getLogger(f"{self.name}_{name}_subprocessProviderLogger")
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.is_file():
            path.unlink()

        path.touch()
        handler = FileHandler(str(path))
        handler.setFormatter(Formatter("%(message)s"))
        logger.addHandler(handler)
        logger.setLevel(logging.DEBUG)
        return logger

    def connect(self):
        """
        Start the process and connect to it.
        Subclasses handle the connection-related tasks.
        """

        if self.is_connected:
            raise ProviderError("Cannot connect twice. Call disconnect before connecting again.")

        # Always disconnect after,
        # unless running tests with `disconnect_providers_after: false`.
        disconnect_after = (
            self._test_runner is None
            or self.config_manager.get_config("test").disconnect_providers_after
        )
        if disconnect_after:
            atexit.register(self.disconnect)

        # Register handlers to ensure atexit handlers are called when Python dies.
        def _signal_handler(signum, frame):
            atexit._run_exitfuncs()
            sys.exit(143 if signum == SIGTERM else 130)

        signal(SIGINT, _signal_handler)
        signal(SIGTERM, _signal_handler)

    def disconnect(self):
        """
        Stop the process if it exists.
        Subclasses override this method to do provider-specific disconnection tasks.
        """

        if self.process:
            self.stop()

    def start(self, timeout: int = 20):
        """Start the process and wait for its RPC to be ready."""

        if self.is_connected:
            logger.info(f"Connecting to existing '{self.process_name}' process.")
            self.process = None  # Not managing the process.
        else:
            logger.info(f"Starting '{self.process_name}' process.")
            pre_exec_fn = _linux_set_death_signal if platform.uname().system == "Linux" else None
            self.stderr_queue = JoinableQueue()
            self.stdout_queue = JoinableQueue()
            out_file = PIPE if logger.level <= LogLevel.DEBUG else DEVNULL
            cmd = self.build_command()
            self.process = Popen(cmd, preexec_fn=pre_exec_fn, stdout=out_file, stderr=out_file)
            spawn(self.produce_stdout_queue)
            spawn(self.produce_stderr_queue)
            spawn(self.consume_stdout_queue)
            spawn(self.consume_stderr_queue)

            with RPCTimeoutError(self, seconds=timeout) as _timeout:
                while True:
                    if self.is_connected:
                        break

                    time.sleep(0.1)
                    _timeout.check()

    def produce_stdout_queue(self):
        process = self.process
        if self.stdout_queue is None or process is None:
            return

        stdout = process.stdout
        if stdout is None:
            return

        for line in iter(stdout.readline, b""):
            self.stdout_queue.put(line)
            time.sleep(0)

    def produce_stderr_queue(self):
        process = self.process
        if self.stderr_queue is None or process is None:
            return

        stderr = process.stderr
        if stderr is None:
            return

        for line in iter(stderr.readline, b""):
            self.stderr_queue.put(line)
            time.sleep(0)

    def consume_stdout_queue(self):
        if self.stdout_queue is None:
            return

        for line in self.stdout_queue:
            output = line.decode("utf8").strip()
            logger.debug(output)
            self._stdout_logger.debug(output)

            if self.stdout_queue is not None:
                self.stdout_queue.task_done()

            time.sleep(0)

    def consume_stderr_queue(self):
        if self.stderr_queue is None:
            return

        for line in self.stderr_queue:
            logger.debug(line.decode("utf8").strip())
            self._stdout_logger.debug(line)

            if self.stderr_queue is not None:
                self.stderr_queue.task_done()

            time.sleep(0)

    def stop(self):
        """Kill the process."""

        if not self.process or self.is_stopping:
            return

        self.is_stopping = True
        logger.info(f"Stopping '{self.process_name}' process.")
        self._kill_process()
        self.is_stopping = False
        self.process = None

    def _wait_for_popen(self, timeout: int = 30):
        if not self.process:
            # Mostly just to make mypy happy.
            raise SubprocessError("Unable to wait for process. It is not set yet.")

        try:
            with SubprocessTimeoutError(self, seconds=timeout) as _timeout:
                while self.process.poll() is None:
                    time.sleep(0.1)
                    _timeout.check()

        except SubprocessTimeoutError:
            pass

    def _kill_process(self):
        if platform.uname().system == "Windows":
            self._windows_taskkill()
            return

        warn_prefix = f"Trying to close '{self.process_name}' process."

        def _try_close(warn_message):
            try:
                if self.process:
                    self.process.send_signal(SIGINT)

                self._wait_for_popen(self.PROCESS_WAIT_TIMEOUT)
            except KeyboardInterrupt:
                logger.warning(warn_message)

        try:
            if self.process is not None and self.process.poll() is None:
                _try_close(f"{warn_prefix}. Press Ctrl+C 1 more times to force quit")

            if self.process is not None and self.process.poll() is None:
                self.process.kill()
                self._wait_for_popen(2)

        except KeyboardInterrupt:
            if self.process is not None:
                self.process.kill()

        self.process = None

    def _windows_taskkill(self) -> None:
        """
        Kills the given process and all child processes using taskkill.exe. Used
        for subprocesses started up on Windows which run in a cmd.exe wrapper that
        doesn't propagate signals by default (leaving orphaned processes).
        """
        process = self.process
        if not process:
            return

        taskkill_bin = shutil.which("taskkill")
        if not taskkill_bin:
            raise SubprocessError("Could not find taskkill.exe executable.")

        proc = Popen(
            [
                taskkill_bin,
                "/F",  # forcefully terminate
                "/T",  # terminate child processes
                "/PID",
                str(process.pid),
            ]
        )
        proc.wait(timeout=self.PROCESS_WAIT_TIMEOUT)


def _linux_set_death_signal():
    """
    Automatically sends SIGTERM to child subprocesses when parent process
    dies (only usable on Linux).
    """
    # from: https://stackoverflow.com/a/43152455/75956
    # the first argument, 1, is the flag for PR_SET_PDEATHSIG
    # the second argument is what signal to send to child subprocesses
    libc = ctypes.CDLL("libc.so.6")
    return libc.prctl(1, SIGTERM)
