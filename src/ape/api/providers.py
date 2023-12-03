import atexit
import ctypes
import datetime
import logging
import platform
import shutil
import sys
import time
from abc import ABC
from concurrent.futures import ThreadPoolExecutor
from copy import copy
from itertools import tee
from logging import FileHandler, Formatter, Logger, getLogger
from pathlib import Path
from signal import SIGINT, SIGTERM, signal
from subprocess import DEVNULL, PIPE, Popen
from typing import Any, Dict, Iterator, List, Optional, Union, cast

from eth_typing import BlockNumber, HexStr
from eth_utils import add_0x_prefix, to_hex
from ethpm_types import HexBytes
from evm_trace import CallTreeNode as EvmCallTreeNode
from evm_trace import TraceFrame as EvmTraceFrame
from web3 import Web3
from web3.exceptions import ContractLogicError as Web3ContractLogicError
from web3.exceptions import MethodUnavailable, TimeExhausted, TransactionNotFound
from web3.types import RPCEndpoint, TxParams

from ape._pydantic_compat import Field, root_validator, validator
from ape.api.config import PluginConfig
from ape.api.networks import LOCAL_NETWORK_NAME, NetworkAPI
from ape.api.query import BlockTransactionQuery
from ape.api.transactions import ReceiptAPI, TransactionAPI
from ape.exceptions import (
    ApeException,
    APINotImplementedError,
    BlockNotFoundError,
    ContractLogicError,
    OutOfGasError,
    ProviderError,
    ProviderNotConnectedError,
    RPCTimeoutError,
    SubprocessError,
    SubprocessTimeoutError,
    TransactionError,
    TransactionNotFoundError,
    VirtualMachineError,
)
from ape.logging import LogLevel, logger, sanitize_url
from ape.types import (
    AddressType,
    AutoGasLimit,
    BlockID,
    CallTreeNode,
    ContractCode,
    ContractLog,
    LogFilter,
    SnapshotID,
    SourceTraceback,
    TraceFrame,
)
from ape.utils import (
    EMPTY_BYTES32,
    BaseInterfaceModel,
    JoinableQueue,
    abstractmethod,
    cached_property,
    gas_estimation_error_message,
    raises_not_implemented,
    run_until_complete,
    spawn,
    to_int,
)
from ape.utils.misc import DEFAULT_MAX_RETRIES_TX, _create_raises_not_implemented_error


class BlockAPI(BaseInterfaceModel):
    """
    An abstract class representing a block and its attributes.
    """

    # NOTE: All fields in this class (and it's subclasses) should not be `Optional`
    #       except the edge cases noted below

    num_transactions: int = 0
    hash: Optional[Any] = None  # NOTE: pending block does not have a hash
    number: Optional[int] = None  # NOTE: pending block does not have a number
    parent_hash: Any = Field(
        EMPTY_BYTES32, alias="parentHash"
    )  # NOTE: genesis block has no parent hash
    size: int
    timestamp: int

    @property
    def datetime(self) -> datetime.datetime:
        return datetime.datetime.fromtimestamp(self.timestamp, tz=datetime.timezone.utc)

    @root_validator(pre=True)
    def convert_parent_hash(cls, data):
        parent_hash = data.get("parent_hash", data.get("parentHash")) or EMPTY_BYTES32
        data["parentHash"] = parent_hash
        return data

    @validator("hash", "parent_hash", pre=True)
    def validate_hexbytes(cls, value):
        # NOTE: pydantic treats these values as bytes and throws an error
        if value and not isinstance(value, bytes):
            return HexBytes(value)

        return value

    @cached_property
    def transactions(self) -> List[TransactionAPI]:
        query = BlockTransactionQuery(columns=["*"], block_id=self.hash)
        return cast(List[TransactionAPI], list(self.query_manager.query(query)))


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

    provider_settings: Dict = {}
    """The settings for the provider, as overrides to the configuration."""

    data_folder: Path
    """The path to the  ``.ape`` directory."""

    request_header: dict
    """A header to set on HTTP/RPC requests."""

    cached_chain_id: Optional[int] = None
    """Implementation providers may use this to cache and re-use chain ID."""

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
    @abstractmethod
    def is_connected(self) -> bool:
        """
        ``True`` if currently connected to the provider. ``False`` otherwise.
        """

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
        data = {**self.config.dict(), **self.provider_settings}
        return CustomConfig.parse_obj(data)

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
    def get_balance(self, address: AddressType) -> int:
        """
        Get the balance of an account.

        Args:
            address (``AddressType``): The address of the account.

        Returns:
            int: The account balance.
        """

    @abstractmethod
    def get_code(self, address: AddressType, **kwargs) -> ContractCode:
        """
        Get the bytes a contract.

        Args:
            address (``AddressType``): The address of the contract.
            **kwargs: Additional, provider-specific kwargs.

        Returns:
            :class:`~ape.types.ContractCode`: The contract bytecode.
        """

    @property
    def network_choice(self) -> str:
        """
        The connected network choice string.
        """
        return f"{self.network.choice}:{self.name}"

    @raises_not_implemented
    def get_storage_at(self, address: AddressType, slot: int) -> bytes:  # type: ignore[empty-body]
        """
        Gets the raw value of a storage slot of a contract.

        Args:
            address (str): The address of the contract.
            slot (int): Storage slot to read the value of.

        Returns:
            bytes: The value of the storage slot.
        """

    @abstractmethod
    def get_nonce(self, address: AddressType) -> int:
        """
        Get the number of times an account has transacted.

        Args:
            address (``AddressType``): The address of the account.

        Returns:
            int
        """

    @abstractmethod
    def estimate_gas_cost(self, txn: TransactionAPI) -> int:
        """
        Estimate the cost of gas for a transaction.

        Args:
            txn (:class:`~ape.api.transactions.TransactionAPI`):
                The transaction to estimate the gas for.

        Returns:
            int: The estimated cost of gas to execute the transaction
            reported in the fee-currency's smallest unit, e.g. Wei.
        """

    @property
    @abstractmethod
    def gas_price(self) -> int:
        """
        The price for what it costs to transact
        (pre-`EIP-1559 <https://eips.ethereum.org/EIPS/eip-1559>`__).
        """

    @property
    def max_gas(self) -> int:
        """
        The max gas limit value you can use.
        """
        # TODO: Make abstract
        return 0

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
    def send_call(self, txn: TransactionAPI, **kwargs) -> bytes:  # Return value of function
        """
        Execute a new transaction call immediately without creating a
        transaction on the blockchain.

        Args:
            txn (:class:`~ape.api.transactions.TransactionAPI`): The transaction
              to send as a call.

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
            account (``AddressType``): The address of the account.
            start_nonce (int): The nonce of the account to start the search with.
            stop_nonce (int): The nonce of the account to stop the search with.

        Returns:
            Iterator[:class:`~ape.api.transactions.ReceiptAPI`]
        """

    @raises_not_implemented
    def get_contract_creation_receipts(  # type: ignore[empty-body]
        self,
        address: AddressType,
        start_block: int = 0,
        stop_block: int = -1,
        contract_code: Optional[HexBytes] = None,
    ) -> Iterator[ReceiptAPI]:
        """
        Get all receipts where a contract address was created or re-created.

        Args:
            address (``AddressType``): The address of the account.
            start_block (int): The block number to start the search with.
            stop_block (int): The block number to stop the search with.
            contract_code (Optional[bytes]): The code of the contract at the stop block.

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
    def revert(self, snapshot_id: SnapshotID):
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

    def __repr__(self) -> str:
        try:
            chain_id = self.chain_id
        except Exception as err:
            logger.error(str(err))
            chain_id = None

        return f"<{self.name} chain_id={self.chain_id}>" if chain_id else f"<{self.name}>"

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
            value: (bytes): The value to overwrite the raw storage slot with.
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
            address (``AddressType``): The address to unlock.

        Returns:
            bool: ``True`` if successfully unlocked account and ``False`` otherwise.
        """

    @raises_not_implemented
    def get_transaction_trace(  # type: ignore[empty-body]
        self, txn_hash: str
    ) -> Iterator[TraceFrame]:
        """
        Provide a detailed description of opcodes.

        Args:
            txn_hash (str): The hash of a transaction to trace.

        Returns:
            Iterator(:class:`~ape.type.trace.TraceFrame`): Transaction execution trace.
        """

    @raises_not_implemented
    def get_call_tree(self, txn_hash: str) -> CallTreeNode:  # type: ignore[empty-body]
        """
        Create a tree structure of calls for a transaction.

        Args:
            txn_hash (str): The hash of a transaction to trace.

        Returns:
            :class:`~ape.types.trace.CallTreeNode`: Transaction execution
            call-tree objects.
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
    def revert(self, snapshot_id: SnapshotID):
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
            contract_src := self.project_manager._create_contract_source(contract_type)
        ):
            return

        method_id = txn.data[:4]
        if method_id in contract_type.view_methods:
            method = contract_type.methods[method_id]
            self._test_runner.coverage_tracker.hit_function(contract_src, method)


def _sanitize_web3_url(msg: str) -> str:
    if "URI: " not in msg:
        return msg

    parts = msg.split("URI: ")
    prefix = parts[0].strip()
    rest = parts[1].split(" ")

    # * To remove the `,` from the url http://127.0.0.1:8545,
    if "," in rest[0]:
        rest[0] = rest[0].rstrip(",")
    sanitized_url = sanitize_url(rest[0])
    return f"{prefix} URI: {sanitized_url} {' '.join(rest[1:])}"


class Web3Provider(ProviderAPI, ABC):
    """
    A base provider mixin class that uses the
    `web3.py <https://web3py.readthedocs.io/en/stable/>`__ python package.
    """

    _web3: Optional[Web3] = None
    _client_version: Optional[str] = None

    def __init__(self, *args, **kwargs):
        logger.create_logger("web3.RequestManager", handlers=(_sanitize_web3_url,))
        logger.create_logger("web3.providers.HTTPProvider", handlers=(_sanitize_web3_url,))
        super().__init__(*args, **kwargs)

    @property
    def web3(self) -> Web3:
        """
        Access to the ``web3`` object as if you did ``Web3(HTTPProvider(uri))``.
        """

        if not self._web3:
            raise ProviderNotConnectedError()

        return self._web3

    @property
    def http_uri(self) -> Optional[str]:
        if (
            hasattr(self.web3.provider, "endpoint_uri")
            and isinstance(self.web3.provider.endpoint_uri, str)
            and self.web3.provider.endpoint_uri.startswith("http")
        ):
            return self.web3.provider.endpoint_uri

        elif hasattr(self, "uri"):
            # NOTE: Some providers define this
            return self.uri

        return None

    @property
    def ws_uri(self) -> Optional[str]:
        if (
            hasattr(self.web3.provider, "endpoint_uri")
            and isinstance(self.web3.provider.endpoint_uri, str)
            and self.web3.provider.endpoint_uri.startswith("ws")
        ):
            return self.web3.provider.endpoint_uri

        return None

    @property
    def client_version(self) -> str:
        if not self._web3:
            return ""

        # NOTE: Gets reset to `None` on `connect()` and `disconnect()`.
        if self._client_version is None:
            self._client_version = self.web3.client_version

        return self._client_version

    @property
    def base_fee(self) -> int:
        latest_block_number = self.get_block("latest").number
        if latest_block_number is None:
            # Possibly no blocks yet.
            logger.debug("Latest block has no number. Using base fee of '0'.")
            return 0

        try:
            fee_history = self.web3.eth.fee_history(1, BlockNumber(latest_block_number))
        except ValueError as exc:
            # Use the less-accurate approach (OK for testing).
            logger.debug(
                "Failed using `web3.eth.fee_history` for network "
                f"'{self.network_choice}'. Error: {exc}"
            )
            return self._get_last_base_fee()

        if len(fee_history["baseFeePerGas"]) < 2:
            logger.debug("Not enough fee_history. Defaulting less-accurate approach.")
            return self._get_last_base_fee()

        pending_base_fee = fee_history["baseFeePerGas"][1]
        if pending_base_fee is None:
            # Non-EIP-1559 chains or we time-travelled pre-London fork.
            return self._get_last_base_fee()

        return pending_base_fee

    def _get_last_base_fee(self) -> int:
        block = self.get_block("latest")
        base_fee = getattr(block, "base_fee", None)
        if base_fee is not None:
            return base_fee

        raise APINotImplementedError("No base fee found in block.")

    @property
    def is_connected(self) -> bool:
        if self._web3 is None:
            return False

        return run_until_complete(self._web3.is_connected())

    @property
    def max_gas(self) -> int:
        block = self.web3.eth.get_block("latest")
        return block["gasLimit"]

    @cached_property
    def supports_tracing(self) -> bool:
        try:
            # NOTE: Txn hash is purposely not a real hash.
            # If we get any exception besides not implemented error,
            # then we support tracing on this provider.
            self.get_call_tree("__CHECK_IF_SUPPORTS_TRACING__")
        except APINotImplementedError:
            return False
        except Exception:
            return True

        return True

    def update_settings(self, new_settings: dict):
        self.disconnect()
        self.provider_settings.update(new_settings)
        self.connect()

    def estimate_gas_cost(self, txn: TransactionAPI, **kwargs) -> int:
        """
        Estimate the cost of gas for a transaction.

        Args:
            txn (:class:`~ape.api.transactions.TransactionAPI`):
                The transaction to estimate the gas for.
            kwargs:
                * ``block_identifier`` (:class:`~ape.types.BlockID`): The block ID
                  to use when estimating the transaction. Useful for checking a
                  past estimation cost of a transaction. Also, you can alias
                  ``block_id``.
                * ``state_overrides`` (Dict): Modify the state of the blockchain
                  prior to estimation.

        Returns:
            int: The estimated cost of gas to execute the transaction
            reported in the fee-currency's smallest unit, e.g. Wei. If the
            provider's network has been configured with a gas limit override, it
            will be returned. If the gas limit configuration is "max" this will
            return the block maximum gas limit.
        """

        txn_dict = txn.dict()

        # Force the use of hex values to support a wider range of nodes.
        if isinstance(txn_dict.get("type"), int):
            txn_dict["type"] = HexBytes(txn_dict["type"]).hex()

        # NOTE: "auto" means to enter this method, so remove it from dict
        if "gas" in txn_dict and (
            txn_dict["gas"] == "auto" or isinstance(txn_dict["gas"], AutoGasLimit)
        ):
            txn_dict.pop("gas")
            # Also pop these, they are overridden by "auto"
            txn_dict.pop("maxFeePerGas", None)
            txn_dict.pop("maxPriorityFeePerGas", None)

        try:
            block_id = kwargs.pop("block_identifier", kwargs.pop("block_id", None))
            txn_params = cast(TxParams, txn_dict)
            return self.web3.eth.estimate_gas(txn_params, block_identifier=block_id)
        except (ValueError, Web3ContractLogicError) as err:
            tx_error = self.get_virtual_machine_error(err, txn=txn)

            # If this is the cause of a would-be revert,
            # raise ContractLogicError so that we can confirm tx-reverts.
            if isinstance(tx_error, ContractLogicError):
                raise tx_error from err

            message = gas_estimation_error_message(tx_error)
            raise TransactionError(
                message, base_err=tx_error, txn=txn, source_traceback=tx_error.source_traceback
            ) from err

    @cached_property
    def chain_id(self) -> int:
        default_chain_id = None
        if (
            self.network.name
            not in (
                "adhoc",
                LOCAL_NETWORK_NAME,
            )
            and not self.network.is_fork
        ):
            # If using a live network, the chain ID is hardcoded.
            default_chain_id = self.network.chain_id

        try:
            if hasattr(self.web3, "eth"):
                return self.web3.eth.chain_id

        except ProviderNotConnectedError:
            if default_chain_id is not None:
                return default_chain_id

            raise  # Original error

        if default_chain_id is not None:
            return default_chain_id

        raise ProviderNotConnectedError()

    @property
    def gas_price(self) -> int:
        price = self.web3.eth.generate_gas_price() or 0
        return to_int(price)

    @property
    def priority_fee(self) -> int:
        try:
            return self.web3.eth.max_priority_fee
        except MethodUnavailable as err:
            # The user likely should be using a more-catered plugin.
            raise APINotImplementedError(
                "eth_maxPriorityFeePerGas not supported in this RPC. Please specify manually."
            ) from err

    def get_block(self, block_id: BlockID) -> BlockAPI:
        if isinstance(block_id, str) and block_id.isnumeric():
            block_id = int(block_id)

        try:
            block_data = dict(self.web3.eth.get_block(block_id))
        except Exception as err:
            raise BlockNotFoundError(block_id, reason=str(err)) from err

        # Some nodes (like anvil) will not have a base fee if set to 0.
        if "baseFeePerGas" in block_data and block_data.get("baseFeePerGas") is None:
            block_data["baseFeePerGas"] = 0

        return self.network.ecosystem.decode_block(block_data)

    def get_nonce(self, address: AddressType, **kwargs) -> int:
        """
        Get the number of times an account has transacted.

        Args:
            address (AddressType): The address of the account.
            kwargs:
                * ``block_identifier`` (:class:`~ape.types.BlockID`): The block ID
                  for checking a previous account nonce. Also, you can use alias
                  ``block_id``.

        Returns:
            int
        """

        block_id = kwargs.pop("block_identifier", kwargs.pop("block_id", None))
        return self.web3.eth.get_transaction_count(address, block_identifier=block_id)

    def get_balance(self, address: AddressType) -> int:
        return self.web3.eth.get_balance(address)

    def get_code(self, address: AddressType, **kwargs) -> ContractCode:
        """
        Get the bytes a contract.

        Args:
            address (``AddressType``): The address of the contract.
            kwargs:
                * ``block_identifier`` (:class:`~ape.types.BlockID`): The block ID
                  for checking a previous account nonce. Also, you can use
                  alias ``block_id``.

        Returns:
            :class:`~ape.types.ContractCode`: The contract bytecode.
        """

        block_id = kwargs.pop("block_identifier", kwargs.pop("block_id", None))
        return self.web3.eth.get_code(address, block_identifier=block_id)

    def get_storage_at(self, address: AddressType, slot: int, **kwargs) -> bytes:
        """
        Gets the raw value of a storage slot of a contract.

        Args:
            address (AddressType): The address of the contract.
            slot (int): Storage slot to read the value of.
            kwargs:
                * ``block_identifier`` (:class:`~ape.types.BlockID`): The block ID
                  for checking previous contract storage values. Also, you can use
                  alias ``block_id``.

        Returns:
            bytes: The value of the storage slot.
        """

        block_id = kwargs.pop("block_identifier", kwargs.pop("block_id", None))
        try:
            return self.web3.eth.get_storage_at(
                address, slot, block_identifier=block_id  # type: ignore
            )
        except ValueError as err:
            if "RPC Endpoint has not been implemented" in str(err):
                raise APINotImplementedError(str(err)) from err

            raise  # Raise original error

    def send_call(self, txn: TransactionAPI, **kwargs) -> bytes:
        """
        Execute a new transaction call immediately without creating a
        transaction on the block chain.

        Args:
            txn: :class:`~ape.api.transactions.TransactionAPI`
            kwargs:
                * ``block_identifier`` (:class:`~ape.types.BlockID`): The block ID
                  to use to send a call at a historical point of a contract. Also,
                  you can us alias ``block_id``.
                  checking a past estimation cost of a transaction.
                * ``state_overrides`` (Dict): Modify the state of the blockchain
                  prior to sending the call, for testing purposes.
                * ``show_trace`` (bool): Set to ``True`` to display the call's
                  trace. Defaults to ``False``.
                * ``show_gas_report (bool): Set to ``True`` to display the call's
                  gas report. Defaults to ``False``.
                * ``skip_trace`` (bool): Set to ``True`` to skip the trace no matter
                  what. This is useful if you are making a more background contract call
                  of some sort, such as proxy-checking, and you are running a global
                  call-tracer such as using the ``--gas`` flag in tests.

        Returns:
            str: The result of the transaction call.
        """
        skip_trace = kwargs.pop("skip_trace", False)
        if skip_trace:
            return self._send_call(txn, **kwargs)

        if self._test_runner is not None:
            track_gas = self._test_runner.gas_tracker.enabled
            track_coverage = self._test_runner.coverage_tracker.enabled
        else:
            track_gas = False
            track_coverage = False

        show_trace = kwargs.pop("show_trace", False)
        show_gas = kwargs.pop("show_gas_report", False)
        needs_trace = track_gas or track_coverage or show_trace or show_gas
        if not needs_trace or not self.provider.supports_tracing or not txn.receiver:
            return self._send_call(txn, **kwargs)

        # The user is requesting information related to a call's trace,
        # such as gas usage data.
        try:
            with self.chain_manager.isolate():
                return self._send_call_as_txn(
                    txn,
                    track_gas=track_gas,
                    track_coverage=track_coverage,
                    show_trace=show_trace,
                    show_gas=show_gas,
                    **kwargs,
                )

        except APINotImplementedError:
            return self._send_call(txn, **kwargs)

    def _send_call_as_txn(
        self,
        txn: TransactionAPI,
        track_gas: bool = False,
        track_coverage: bool = False,
        show_trace: bool = False,
        show_gas: bool = False,
        **kwargs,
    ) -> bytes:
        account = self.account_manager.test_accounts[0]
        receipt = account.call(txn, **kwargs)
        if not (call_tree := receipt.call_tree):
            return self._send_call(txn, **kwargs)

        # Grab raw returndata before enrichment
        returndata = call_tree.outputs

        if (track_gas or track_coverage) and show_gas and not show_trace:
            # Optimization to enrich early and in_place=True.
            call_tree.enrich()

        if track_gas:
            # in_place=False in case show_trace is True
            receipt.track_gas()

        if track_coverage:
            receipt.track_coverage()

        if show_gas:
            # in_place=False in case show_trace is True
            self.chain_manager._reports.show_gas(call_tree.enrich(in_place=False))

        if show_trace:
            call_tree = call_tree.enrich(use_symbol_for_tokens=True)
            self.chain_manager._reports.show_trace(call_tree)

        return HexBytes(returndata)

    def _send_call(self, txn: TransactionAPI, **kwargs) -> bytes:
        arguments = self._prepare_call(txn, **kwargs)
        try:
            return self._eth_call(arguments)
        except TransactionError as err:
            if not err.txn:
                err.txn = txn

            raise  # The tx error

    def _eth_call(self, arguments: List) -> bytes:
        # Force the usage of hex-type to support a wider-range of nodes.
        txn_dict = copy(arguments[0])
        if isinstance(txn_dict.get("type"), int):
            txn_dict["type"] = HexBytes(txn_dict["type"]).hex()

        # Remove unnecessary values to support a wider-range of nodes.
        txn_dict.pop("chainId", None)

        arguments[0] = txn_dict
        try:
            result = self._make_request("eth_call", arguments)
        except Exception as err:
            receiver = txn_dict["to"]
            raise self.get_virtual_machine_error(err, contract_address=receiver) from err

        if "error" in result:
            raise ProviderError(result["error"]["message"])

        return HexBytes(result)

    def _prepare_call(self, txn: TransactionAPI, **kwargs) -> List:
        txn_dict = txn.dict()
        fields_to_convert = ("data", "chainId", "value")
        for field in fields_to_convert:
            value = txn_dict.get(field)
            if value is not None and not isinstance(value, str):
                txn_dict[field] = to_hex(value)

        # Remove unneeded properties
        txn_dict.pop("gas", None)
        txn_dict.pop("gasLimit", None)
        txn_dict.pop("maxFeePerGas", None)
        txn_dict.pop("maxPriorityFeePerGas", None)

        block_identifier = kwargs.pop("block_identifier", kwargs.pop("block_id", "latest"))
        if isinstance(block_identifier, int):
            block_identifier = to_hex(block_identifier)

        arguments = [txn_dict, block_identifier]
        if "state_override" in kwargs:
            arguments.append(kwargs["state_override"])

        return arguments

    def get_receipt(
        self,
        txn_hash: str,
        required_confirmations: int = 0,
        timeout: Optional[int] = None,
        **kwargs,
    ) -> ReceiptAPI:
        """
        Get the information about a transaction from a transaction hash.

        Args:
            txn_hash (str): The hash of the transaction to retrieve.
            required_confirmations (int): The amount of block confirmations
              to wait before returning the receipt. Defaults to ``0``.
            timeout (Optional[int]): The amount of time to wait for a receipt
              before timing out. Defaults ``None``.

        Raises:
            :class:`~ape.exceptions.TransactionNotFoundError`: Likely the exception raised
              when the transaction receipt is not found (depends on implementation).

        Returns:
            :class:`~api.providers.ReceiptAPI`:
            The receipt of the transaction with the given hash.
        """

        if required_confirmations < 0:
            raise TransactionError("Required confirmations cannot be negative.")

        timeout = (
            timeout if timeout is not None else self.provider.network.transaction_acceptance_timeout
        )

        try:
            receipt_data = self.web3.eth.wait_for_transaction_receipt(
                HexBytes(txn_hash), timeout=timeout
            )
        except TimeExhausted as err:
            raise TransactionNotFoundError(txn_hash, error_messsage=str(err)) from err

        network_config: Dict = self.network.config.dict().get(self.network.name, {})
        max_retries = network_config.get("max_get_transaction_retries", DEFAULT_MAX_RETRIES_TX)
        txn = {}
        for attempt in range(max_retries):
            try:
                txn = dict(self.web3.eth.get_transaction(HexStr(txn_hash)))
                break
            except TransactionNotFound:
                if attempt < max_retries - 1:  # if this wasn't the last attempt
                    time.sleep(1)  # Wait for 1 second before retrying.
                    continue  # Continue to the next iteration, effectively retrying the operation.
                else:  # if it was the last attempt
                    raise  # Re-raise the last exception.

        receipt = self.network.ecosystem.decode_receipt(
            {
                "provider": self,
                "required_confirmations": required_confirmations,
                **txn,
                **receipt_data,
            }
        )
        return receipt.await_confirmations()

    def get_transactions_by_block(self, block_id: BlockID) -> Iterator[TransactionAPI]:
        if isinstance(block_id, str):
            block_id = HexStr(block_id)

            if block_id.isnumeric():
                block_id = add_0x_prefix(block_id)

        block = cast(Dict, self.web3.eth.get_block(block_id, full_transactions=True))
        for transaction in block.get("transactions", []):
            yield self.network.ecosystem.create_transaction(**transaction)

    def get_transactions_by_account_nonce(
        self,
        account: AddressType,
        start_nonce: int = 0,
        stop_nonce: int = -1,
    ) -> Iterator[ReceiptAPI]:
        if start_nonce > stop_nonce:
            raise ValueError("Starting nonce cannot be greater than stop nonce for search")

        if self.network.name != LOCAL_NETWORK_NAME and (stop_nonce - start_nonce) > 2:
            # NOTE: RPC usage might be acceptable to find 1 or 2 transactions reasonably quickly
            logger.warning(
                "Performing this action is likely to be very slow and may "
                f"use {20 * (stop_nonce - start_nonce)} or more RPC calls. "
                "Consider installing an alternative data query provider plugin."
            )

        yield from self._find_txn_by_account_and_nonce(
            account,
            start_nonce,
            stop_nonce,
            0,  # first block
            self.chain_manager.blocks.head.number or 0,  # last block (or 0 if genesis-only chain)
        )

    def _find_txn_by_account_and_nonce(
        self,
        account: AddressType,
        start_nonce: int,
        stop_nonce: int,
        start_block: int,
        stop_block: int,
    ) -> Iterator[ReceiptAPI]:
        # binary search between `start_block` and `stop_block` to yield txns from account,
        # ordered from `start_nonce` to `stop_nonce`

        if start_block == stop_block:
            # Honed in on one block where there's a delta in nonce, so must be the right block
            for txn in self.get_transactions_by_block(stop_block):
                assert isinstance(txn.nonce, int)  # NOTE: just satisfying mypy here
                if txn.sender == account and txn.nonce >= start_nonce:
                    yield self.get_receipt(txn.txn_hash.hex())

            # Nothing else to search for

        else:
            # Break up into smaller chunks
            # NOTE: biased to `stop_block`
            block_number = start_block + (stop_block - start_block) // 2 + 1
            txn_count_prev_to_block = self.web3.eth.get_transaction_count(account, block_number - 1)

            if start_nonce < txn_count_prev_to_block:
                yield from self._find_txn_by_account_and_nonce(
                    account,
                    start_nonce,
                    min(txn_count_prev_to_block - 1, stop_nonce),  # NOTE: In case >1 txn in block
                    start_block,
                    block_number - 1,
                )

            if txn_count_prev_to_block <= stop_nonce:
                yield from self._find_txn_by_account_and_nonce(
                    account,
                    max(start_nonce, txn_count_prev_to_block),  # NOTE: In case >1 txn in block
                    stop_nonce,
                    block_number,
                    stop_block,
                )

    def block_ranges(self, start=0, stop=None, page=None):
        if stop is None:
            stop = self.chain_manager.blocks.height
        if page is None:
            page = self.block_page_size

        for start_block in range(start, stop + 1, page):
            stop_block = min(stop, start_block + page - 1)
            yield start_block, stop_block

    def get_contract_creation_receipts(
        self,
        address: AddressType,
        start_block: int = 0,
        stop_block: Optional[int] = None,
        contract_code: Optional[HexBytes] = None,
    ) -> Iterator[ReceiptAPI]:
        if stop_block is None:
            stop_block = self.chain_manager.blocks.height

        if contract_code is None:
            contract_code = HexBytes(self.get_code(address))

        mid_block = (stop_block - start_block) // 2 + start_block
        # NOTE: biased towards mid_block == start_block

        if start_block == mid_block:
            for tx in self.chain_manager.blocks[mid_block].transactions:
                if (receipt := tx.receipt) and receipt.contract_address == address:
                    yield receipt

            if mid_block + 1 <= stop_block:
                yield from self.get_contract_creation_receipts(
                    address,
                    start_block=mid_block + 1,
                    stop_block=stop_block,
                    contract_code=contract_code,
                )

        # TODO: Handle when code is nonzero but doesn't match
        # TODO: Handle when code is empty after it's not (re-init)
        elif HexBytes(self.get_code(address, block_id=mid_block)) == contract_code:
            # If the code exists, we need to look backwards.
            yield from self.get_contract_creation_receipts(
                address,
                start_block=start_block,
                stop_block=mid_block,
                contract_code=contract_code,
            )

        elif mid_block + 1 <= stop_block:
            # The code does not exist yet, we need to look ahead.
            yield from self.get_contract_creation_receipts(
                address,
                start_block=mid_block + 1,
                stop_block=stop_block,
                contract_code=contract_code,
            )

    def get_contract_logs(self, log_filter: LogFilter) -> Iterator[ContractLog]:
        height = self.chain_manager.blocks.height
        start_block = log_filter.start_block
        stop_block_arg = log_filter.stop_block if log_filter.stop_block is not None else height
        stop_block = min(stop_block_arg, height)
        block_ranges = self.block_ranges(start_block, stop_block, self.block_page_size)

        def fetch_log_page(block_range):
            start, stop = block_range
            page_filter = log_filter.copy(update=dict(start_block=start, stop_block=stop))
            # eth-tester expects a different format, let web3 handle the conversions for it
            raw = "EthereumTester" not in self.client_version
            logs = self._get_logs(page_filter.dict(), raw)
            return self.network.ecosystem.decode_logs(logs, *log_filter.events)

        with ThreadPoolExecutor(self.concurrency) as pool:
            for page in pool.map(fetch_log_page, block_ranges):
                yield from page

    def _get_logs(self, filter_params, raw=True) -> List[Dict]:
        if not raw:
            return [vars(d) for d in self.web3.eth.get_logs(filter_params)]

        return self._make_request("eth_getLogs", [filter_params])

    def prepare_transaction(self, txn: TransactionAPI) -> TransactionAPI:
        # NOTE: Use "expected value" for Chain ID, so if it doesn't match actual, we raise
        txn.chain_id = self.network.chain_id

        from ape_ethereum.transactions import StaticFeeTransaction, TransactionType

        txn_type = TransactionType(txn.type)
        if (
            txn_type == TransactionType.STATIC
            and isinstance(txn, StaticFeeTransaction)
            and txn.gas_price is None
        ):
            txn.gas_price = self.gas_price
        elif txn_type == TransactionType.DYNAMIC:
            if txn.max_priority_fee is None:
                txn.max_priority_fee = self.priority_fee

            if txn.max_fee is None:
                multiplier = self.network.base_fee_multiplier
                txn.max_fee = int(self.base_fee * multiplier + txn.max_priority_fee)
            # else: Assume user specified the correct amount or txn will fail and waste gas

        gas_limit = self.network.gas_limit if txn.gas_limit is None else txn.gas_limit
        if gas_limit in (None, "auto") or isinstance(gas_limit, AutoGasLimit):
            multiplier = (
                gas_limit.multiplier
                if isinstance(gas_limit, AutoGasLimit)
                else self.network.auto_gas_multiplier
            )
            if multiplier != 1.0:
                gas = min(int(self.estimate_gas_cost(txn) * multiplier), self.max_gas)
            else:
                gas = self.estimate_gas_cost(txn)

            txn.gas_limit = gas

        elif gas_limit == "max":
            txn.gas_limit = self.max_gas

        elif gas_limit is not None and isinstance(gas_limit, int):
            txn.gas_limit = gas_limit

        if txn.required_confirmations is None:
            txn.required_confirmations = self.network.required_confirmations
        elif not isinstance(txn.required_confirmations, int) or txn.required_confirmations < 0:
            raise TransactionError("'required_confirmations' must be a positive integer.")

        return txn

    def send_transaction(self, txn: TransactionAPI) -> ReceiptAPI:
        try:
            if txn.signature or not txn.sender:
                txn_hash = self.web3.eth.send_raw_transaction(txn.serialize_transaction())
            else:
                if txn.sender not in self.web3.eth.accounts:
                    self.chain_manager.provider.unlock_account(txn.sender)

                txn_hash = self.web3.eth.send_transaction(cast(TxParams, txn.dict()))

        except (ValueError, Web3ContractLogicError) as err:
            vm_err = self.get_virtual_machine_error(err, txn=txn)
            raise vm_err from err

        receipt = self.get_receipt(
            txn_hash.hex(),
            required_confirmations=(
                txn.required_confirmations
                if txn.required_confirmations is not None
                else self.network.required_confirmations
            ),
        )

        # NOTE: Ensure to cache even the failed receipts.
        self.chain_manager.history.append(receipt)

        if receipt.failed:
            txn_dict = receipt.transaction.dict()
            txn_params = cast(TxParams, txn_dict)

            # Replay txn to get revert reason
            try:
                self.web3.eth.call(txn_params)
            except Exception as err:
                vm_err = self.get_virtual_machine_error(err, txn=txn)
                vm_err.txn = txn
                raise vm_err from err

        logger.info(f"Confirmed {receipt.txn_hash} (total fees paid = {receipt.total_fees_paid})")
        return receipt

    def _create_call_tree_node(
        self, evm_call: EvmCallTreeNode, txn_hash: Optional[str] = None
    ) -> CallTreeNode:
        address = evm_call.address
        try:
            contract_id = str(self.provider.network.ecosystem.decode_address(address))
        except ValueError:
            # Use raw value since it is not a real address.
            contract_id = address.hex()

        call_type_str: str = getattr(evm_call.call_type, "value", f"{evm_call.call_type}")
        input_data = evm_call.calldata if "CREATE" in call_type_str else evm_call.calldata[4:].hex()
        return CallTreeNode(
            calls=[self._create_call_tree_node(x, txn_hash=txn_hash) for x in evm_call.calls],
            call_type=call_type_str,
            contract_id=contract_id,
            failed=evm_call.failed,
            gas_cost=evm_call.gas_cost,
            inputs=input_data,
            method_id=evm_call.calldata[:4].hex(),
            outputs=evm_call.returndata.hex(),
            raw=evm_call.dict(),
            txn_hash=txn_hash,
        )

    def _create_trace_frame(self, evm_frame: EvmTraceFrame) -> TraceFrame:
        address_bytes = evm_frame.address
        try:
            address = (
                self.network.ecosystem.decode_address(address_bytes.hex())
                if address_bytes
                else None
            )
        except ValueError:
            # Might not be a real address.
            address = cast(AddressType, address_bytes.hex()) if address_bytes else None

        return TraceFrame(
            pc=evm_frame.pc,
            op=evm_frame.op,
            gas=evm_frame.gas,
            gas_cost=evm_frame.gas_cost,
            depth=evm_frame.depth,
            contract_address=address,
            raw=evm_frame.dict(),
        )

    def _make_request(self, endpoint: str, parameters: Optional[List] = None) -> Any:
        parameters = parameters or []
        coroutine = self.web3.provider.make_request(RPCEndpoint(endpoint), parameters)
        result = run_until_complete(coroutine)

        if "error" in result:
            error = result["error"]
            message = (
                error["message"] if isinstance(error, dict) and "message" in error else str(error)
            )
            raise ProviderError(message)

        elif "result" in result:
            return result.get("result", {})

        return result

    def get_virtual_machine_error(self, exception: Exception, **kwargs) -> VirtualMachineError:
        """
        Get a virtual machine error from an error returned from your RPC.
        If from a contract revert / assert statement, you will be given a
        special :class:`~ape.exceptions.ContractLogicError` that can be
        checked in ``ape.reverts()`` tests.

        **NOTE**: The default implementation is based on ``geth`` output.
        ``ProviderAPI`` implementations override when needed.

        Args:
            exception (Exception): The error returned from your RPC client.

        Returns:
            :class:`~ape.exceptions.VirtualMachineError`: An error representing what
               went wrong in the call.
        """

        txn = kwargs.get("txn")
        if isinstance(exception, Web3ContractLogicError):
            # This happens from `assert` or `require` statements.
            return self._handle_execution_reverted(exception, **kwargs)

        if not len(exception.args):
            return VirtualMachineError(base_err=exception, **kwargs)

        err_data = exception.args[0] if (hasattr(exception, "args") and exception.args) else None
        if isinstance(err_data, str) and "execution reverted" in err_data:
            return self._handle_execution_reverted(exception, **kwargs)

        if not isinstance(err_data, dict):
            return VirtualMachineError(base_err=exception, **kwargs)

        if not (err_msg := err_data.get("message")):
            return VirtualMachineError(base_err=exception, **kwargs)

        if txn is not None and "nonce too low" in str(err_msg):
            txn = cast(TransactionAPI, txn)
            new_err_msg = f"Nonce '{txn.nonce}' is too low"
            return VirtualMachineError(
                new_err_msg, base_err=exception, code=err_data.get("code"), **kwargs
            )

        elif "out of gas" in str(err_msg):
            return OutOfGasError(code=err_data.get("code"), base_err=exception, **kwargs)

        return VirtualMachineError(str(err_msg), code=err_data.get("code"), **kwargs)

    def _handle_execution_reverted(
        self,
        exception: Union[Exception, str],
        txn: Optional[TransactionAPI] = None,
        trace: Optional[Iterator[TraceFrame]] = None,
        contract_address: Optional[AddressType] = None,
        source_traceback: Optional[SourceTraceback] = None,
    ) -> ContractLogicError:
        message = str(exception).split(":")[-1].strip()
        params: Dict = {
            "trace": trace,
            "contract_address": contract_address,
            "source_traceback": source_traceback,
        }
        no_reason = message == "execution reverted"

        if isinstance(exception, Web3ContractLogicError) and no_reason:
            # Check for custom exception data and use that as the message instead.
            # This allows compiler exception enrichment to function.
            err_trace = None
            try:
                if trace:
                    trace, err_trace = tee(trace)
                elif txn:
                    err_trace = self.provider.get_transaction_trace(txn.txn_hash.hex())

                trace_ls: List[TraceFrame] = list(err_trace) if err_trace else []
                data = trace_ls[-1].raw if len(trace_ls) > 0 else {}
                memory = data.get("memory", [])
                return_value = "".join([x[2:] for x in memory[4:]])
                if return_value:
                    message = f"0x{return_value}"
                    no_reason = False

            except (ApeException, NotImplementedError):
                # Either provider does not support or isn't a custom exception.
                pass

        result = (
            ContractLogicError(txn=txn, **params)
            if no_reason
            else ContractLogicError(
                base_err=exception if isinstance(exception, Exception) else None,
                revert_message=message,
                txn=txn,
                **params,
            )
        )
        return self.compiler_manager.enrich_error(result)


class UpstreamProvider(ProviderAPI):
    """
    A provider that can also be set as another provider's upstream.
    """

    @property
    @abstractmethod
    def connection_str(self) -> str:
        """
        The str used by downstream providers to connect to this one.
        For example, the URL for HTTP-based providers.
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
    def build_command(self) -> List[str]:
        """
        Get the command as a list of ``str``.
        Subclasses should override and add command arguments if needed.

        Returns:
            List[str]: The command to pass to ``subprocess.Popen``.
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

        self.cached_chain_id = None
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
