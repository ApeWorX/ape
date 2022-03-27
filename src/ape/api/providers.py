import atexit
import ctypes
import platform
import shutil
import sys
import time
from abc import ABC
from pathlib import Path
from signal import SIGINT, SIGTERM, signal
from subprocess import PIPE, Popen, call
from typing import Any, Callable, Dict, Iterator, List, Optional, Union

from eth_abi.abi import encode_single
from eth_typing import HexStr
from eth_utils import add_0x_prefix, keccak
from ethpm_types.abi import EventABI
from evm_trace import TraceFrame
from hexbytes import HexBytes
from pydantic import Field, validator
from web3 import Web3

from ape.api.config import PluginConfig
from ape.api.networks import NetworkAPI
from ape.api.transactions import ReceiptAPI, TransactionAPI, TransactionType
from ape.contracts._utils import LogInputABICollection
from ape.exceptions import (
    DecodingError,
    ProviderError,
    RPCTimeoutError,
    SubprocessError,
    SubprocessTimeoutError,
    TransactionError,
)
from ape.logging import logger
from ape.types import AddressType, BlockID, ContractLog, SnapshotID
from ape.utils import BaseInterfaceModel, abstractmethod, cached_property, raises_not_implemented


class BlockGasAPI(BaseInterfaceModel):
    """
    An abstract class for representing gas data for a block.
    """

    gas_limit: int = Field(alias="gasLimit")
    gas_used: int = Field(alias="gasUsed")
    base_fee: Optional[int] = Field(None, alias="baseFeePerGas")


class BlockConsensusAPI(BaseInterfaceModel):
    """
    An abstract class representing block consensus-data,
    such as PoW-related information regarding the block.
    `EIP-3675 <https://eips.ethereum.org/EIPS/eip-3675>`__.
    """

    difficulty: Optional[int] = None
    total_difficulty: Optional[int] = Field(None, alias="totalDifficulty")


class BlockAPI(BaseInterfaceModel):
    """
    An abstract class representing a block and its attributes.
    """

    gas_data: BlockGasAPI
    consensus_data: BlockConsensusAPI
    hash: Optional[Any] = None
    number: Optional[int] = None
    parent_hash: Optional[Any] = None
    size: int
    timestamp: int

    @validator("hash", "parent_hash", pre=True)
    def validate_hexbytes(cls, value):
        # NOTE: pydantic treats these values as bytes and throws an error
        if value and not isinstance(value, HexBytes):
            raise ValueError(f"Hash `{value}` is not a valid Hexbyte.")
        return value


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

    provider_settings: dict
    """The settings for the provider, as overrides to the configuration."""

    data_folder: Path
    """The path to the  ``.ape`` directory."""

    request_header: dict
    """A header to set on HTTP/RPC requests."""

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
    def get_balance(self, address: str) -> int:
        """
        Get the balance of an account.

        Args:
            address (str): The address of the account.

        Returns:
            int: The account balance.
        """

    @abstractmethod
    def get_code(self, address: str) -> bytes:
        """
        Get the bytes a contract.

        Args:
            address (str): The address of the contract.

        Returns:
            bytes: The contract byte-code.
        """

    @abstractmethod
    def get_nonce(self, address: str) -> int:
        """
        Get the number of times an account has transacted.

        Args:
            address (str): The address of the account.

        Returns:
            int
        """

    @abstractmethod
    def estimate_gas_cost(self, txn: TransactionAPI) -> int:
        """
        Estimate the cost of gas for a transaction.

        Args:
            txn (:class:`~ape.api.providers.TransactionAPI`):
                The transaction to estimate the gas for.

        Returns:
            int: The estimated cost of gas.
        """

    @property
    @abstractmethod
    def gas_price(self) -> int:
        """
        The price for what it costs to transact
        (pre-`EIP-1559 <https://eips.ethereum.org/EIPS/eip-1559>`__).
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
        raise NotImplementedError("priority_fee is not implemented by this provider")

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
        raise NotImplementedError("base_fee is not implemented by this provider")

    @abstractmethod
    def get_block(self, block_id: BlockID) -> BlockAPI:
        """
        Get a block.

        Args:
            block_id (:class:`~ape.types.BlockID`): The ID of the block to get.
                Can be ``"latest"``, ``"earliest"``, ``"pending"``, a block hash or a block number.

        Returns:
            :class:`~ape.types.BlockID`: The block for the given ID.
        """

    @abstractmethod
    def send_call(self, txn: TransactionAPI) -> bytes:  # Return value of function
        """
        Execute a new transaction call immediately without creating a
        transaction on the block chain.

        Args:
            txn: :class:`~ape.api.providers.TransactionAPI`

        Returns:
            str: The result of the transaction call.
        """

    @abstractmethod
    def get_transaction(self, txn_hash: str) -> ReceiptAPI:
        """
        Get the information about a transaction from a transaction hash.

        Args:
            txn_hash (str): The hash of the transaction to retrieve.

        Returns:
            :class:`~api.providers.ReceiptAPI`:
            The receipt of the transaction with the given hash.
        """

    @abstractmethod
    def send_transaction(self, txn: TransactionAPI) -> ReceiptAPI:
        """
        Send a transaction to the network.

        Args:
            txn (:class:`~ape.api.providers.TransactionAPI`): The transaction to send.

        Returns:
            :class:`~ape.api.providers.ReceiptAPI`
        """

    @abstractmethod
    def get_contract_logs(
        self,
        address: Union[AddressType, List[AddressType]],
        abi: Union[EventABI, List[EventABI]],
        start_block: Optional[int] = None,
        stop_block: Optional[int] = None,
        block_page_size: Optional[int] = None,
        event_parameters: Optional[Dict] = None,
    ) -> Iterator[ContractLog]:
        """
        Get all logs matching the given set of filter parameters.

        Args:
            address (``AddressType``): The contract address that defines the logs.
            abi (``EventABI``): The event of interest's ABI.
            start_block (Optional[int]): Get events that occurred
              in blocks after the block with this ID.
            stop_block (Optional[int]): Get events that occurred
              in blocks before the block with this ID.
            block_page_size (Optional[int]): Use this parameter to adjust
              request block range sizes.
            event_parameters (Optional[Dict]): Filter by event parameter values.

        Returns:
            Iterator[:class:`~ape.contracts.base.ContractLog`]
        """

    @raises_not_implemented
    def snapshot(self) -> SnapshotID:
        """
        Defined to make the ``ProviderAPI`` interchangeable with a
        :class:`~ape.api.providers.TestProviderAPI`, as in
        :class:`ape.managers.chain.ChainManager`.

        Raises:
            NotImplementedError: Unless overridden.
        """

    @raises_not_implemented
    def revert(self, snapshot_id: SnapshotID):
        """
        Defined to make the ``ProviderAPI`` interchangeable with a
        :class:`~ape.api.providers.TestProviderAPI`, as in
        :class:`ape.managers.chain.ChainManager`.

        Raises:
            NotImplementedError: Unless overridden.
        """

    @raises_not_implemented
    def set_timestamp(self, new_timestamp: int):
        """
        Defined to make the ``ProviderAPI`` interchangeable with a
        :class:`~ape.api.providers.TestProviderAPI`, as in
        :class:`ape.managers.chain.ChainManager`.

        Raises:
            NotImplementedError: Unless overridden.
        """

    @raises_not_implemented
    def mine(self, num_blocks: int = 1):
        """
        Defined to make the ``ProviderAPI`` interchangeable with a
        :class:`~ape.api.providers.TestProviderAPI`, as in
        :class:`ape.managers.chain.ChainManager`.

        Raises:
            NotImplementedError: Unless overridden.
        """

    def __repr__(self) -> str:
        return f"<{self.name} chain_id={self.chain_id}>"

    @raises_not_implemented
    def unlock_account(self, address: AddressType) -> bool:
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
    def get_transaction_trace(self, txn_hash: str) -> Iterator[TraceFrame]:
        """
        Provide a detailed description of opcodes.

        Args:
            txn_hash (str): The hash of a transaction to trace.

        Returns:
            Iterator(TraceFrame): Transaction execution trace object.
        """

    def prepare_transaction(self, txn: TransactionAPI) -> TransactionAPI:
        """
        Set default values on the transaction.

        Raises:
            :class:`~ape.exceptions.TransactionError`: When given negative required confirmations.

        Args:
            txn (:class:`~ape.api.providers.TransactionAPI`): The transaction to prepare.

        Returns:
            :class:`~ape.api.providers.TransactionAPI`
        """

        # NOTE: Use "expected value" for Chain ID, so if it doesn't match actual, we raise
        txn.chain_id = self.network.chain_id

        txn_type = TransactionType(txn.type)
        if txn_type == TransactionType.STATIC and txn.gas_price is None:  # type: ignore
            txn.gas_price = self.gas_price  # type: ignore
        elif txn_type == TransactionType.DYNAMIC:
            if txn.max_priority_fee is None:  # type: ignore
                txn.max_priority_fee = self.priority_fee  # type: ignore

            if txn.max_fee is None:
                txn.max_fee = self.base_fee + txn.max_priority_fee
            # else: Assume user specified the correct amount or txn will fail and waste gas

        if txn.gas_limit is None:
            txn.gas_limit = self.estimate_gas_cost(txn)
        # else: Assume user specified the correct amount or txn will fail and waste gas

        if txn.required_confirmations is None:
            txn.required_confirmations = self.network.required_confirmations
        elif not isinstance(txn.required_confirmations, int) or txn.required_confirmations < 0:
            raise TransactionError(message="'required_confirmations' must be a positive integer.")

        return txn

    def _try_track_receipt(self, receipt: ReceiptAPI):
        if self.chain_manager:
            self.chain_manager.account_history.append(receipt)


class TestProviderAPI(ProviderAPI):
    """
    An API for providers that have development functionality, such as snapshotting.
    """

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

    @cached_property
    def test_config(self) -> PluginConfig:
        return self.config_manager.get_config("test")


class Web3Provider(ProviderAPI, ABC):
    """
    A base provider mixin class that uses the
    [web3.py](https://web3py.readthedocs.io/en/stable/) python package.
    """

    _web3: Web3 = None  # type: ignore

    def update_settings(self, new_settings: dict):
        self.disconnect()
        self.provider_settings.update(new_settings)
        self.connect()

    def estimate_gas_cost(self, txn: TransactionAPI) -> int:
        txn_dict = txn.dict()
        return self._web3.eth.estimate_gas(txn_dict)  # type: ignore

    @property
    def chain_id(self) -> int:
        if hasattr(self._web3, "eth"):
            return self._web3.eth.chain_id
        else:
            return self.network.chain_id

    @property
    def gas_price(self) -> int:
        return self._web3.eth.generate_gas_price()  # type: ignore

    @property
    def priority_fee(self) -> int:
        return self._web3.eth.max_priority_fee

    @property
    def base_fee(self) -> int:
        block = self.get_block("latest")

        if block.gas_data.base_fee is None:
            # Non-EIP-1559 chains or we time-travelled pre-London fork.
            raise NotImplementedError("base_fee is not implemented by this provider.")

        return block.gas_data.base_fee

    def get_block(self, block_id: BlockID) -> BlockAPI:
        if isinstance(block_id, str):
            block_id = HexStr(block_id)

            if block_id.isnumeric():
                block_id = add_0x_prefix(block_id)

        block_data = self._web3.eth.get_block(block_id)
        return self.network.ecosystem.decode_block(block_data)  # type: ignore

    def get_nonce(self, address: str) -> int:
        return self._web3.eth.get_transaction_count(address)  # type: ignore

    def get_balance(self, address: str) -> int:
        return self._web3.eth.get_balance(address)  # type: ignore

    def get_code(self, address: str) -> bytes:
        return self._web3.eth.get_code(address)  # type: ignore

    def send_call(self, txn: TransactionAPI) -> bytes:
        return self._web3.eth.call(txn.dict())

    def get_transaction(self, txn_hash: str, required_confirmations: int = 0) -> ReceiptAPI:
        if required_confirmations < 0:
            raise TransactionError(message="Required confirmations cannot be negative.")

        receipt_data = self._web3.eth.wait_for_transaction_receipt(HexBytes(txn_hash))
        txn = self._web3.eth.get_transaction(txn_hash)  # type: ignore
        receipt = self.network.ecosystem.decode_receipt(
            {
                "provider": self,
                "required_confirmations": required_confirmations,
                **txn,
                **receipt_data,
            }
        )
        return receipt.await_confirmations()

    def get_contract_logs(
        self,
        address: Union[AddressType, List[AddressType]],
        abi: Union[List[EventABI], EventABI],
        start_block: Optional[int] = None,
        stop_block: Optional[int] = None,
        block_page_size: Optional[int] = None,
        event_parameters: Optional[Dict] = None,
    ) -> Iterator[ContractLog]:
        if block_page_size is not None:
            if block_page_size < 0:
                raise ValueError("'block_page_size' cannot be negative.")
        else:
            block_page_size = 100

        event_parameters = event_parameters or {}
        height = self.chain_manager.blocks.height

        required_confirmations = self.provider.network.required_confirmations
        stop_block = height - required_confirmations if stop_block is None else stop_block
        if stop_block > height:
            raise ValueError(f"Stop-block '{stop_block}' greater than height '{height}'.")

        start_block = start_block or 0
        if start_block > stop_block:
            raise ValueError(
                f"Start block '{start_block}' cannot be greater than stop block '{stop_block}'."
            )

        start = start_block
        stop_increment = block_page_size - 1
        stop = min(start + stop_increment, stop_block)

        while start <= stop_block:
            logs = [
                log
                for log in self._get_logs_in_block_range(
                    address,
                    abi,
                    start_block=start,
                    stop_block=stop,
                    block_page_size=block_page_size,
                    event_parameters=event_parameters,
                )
            ]

            if len(logs) == 0:
                # No events happened in this sub-block range. Go to next page.
                start = stop + 1

                if start < stop_block:
                    stop = start + stop_increment
                elif start == stop_block:
                    stop = start

                continue

            for log in logs:
                yield log

            # Start the next iteration on the largest block number to get remaining events.
            start = stop + 1
            stop = min(start + stop_increment, stop_block)

    def _get_logs_in_block_range(
        self,
        address: Union[AddressType, List[AddressType]],
        abi: Union[List[EventABI], EventABI],
        start_block: Optional[int] = None,
        stop_block: Optional[int] = None,
        block_page_size: Optional[int] = None,
        event_parameters: Optional[Dict] = None,
    ):
        start_block = start_block or 0
        abis = abi if isinstance(abi, (list, tuple)) else [abi]
        block_page_size = block_page_size or 100
        stop_block = start_block + block_page_size if stop_block is None else stop_block
        event_parameters = event_parameters or {}
        for abi in abis:
            if not isinstance(address, (list, tuple)):
                address = [address]

            addresses = [self.conversion_manager.convert(a, AddressType) for a in address]
            log_filter: Dict = {
                "address": addresses,
                "fromBlock": start_block,
                "toBlock": stop_block,
                "topics": [],
            }

            if "topics" not in event_parameters:
                event_signature_hash = add_0x_prefix(HexStr(keccak(text=abi.selector).hex()))
                log_filter["topics"] = [event_signature_hash]
                search_topics = []
                abi_types = []
                topics = LogInputABICollection(
                    abi, [abi_input for abi_input in abi.inputs if abi_input.indexed]
                )

                for name, arg in event_parameters.items():
                    if hasattr(arg, "address"):
                        arg = self.conversion_manager.convert(arg, AddressType)

                    abi_type = None
                    for argument in topics.values:
                        if argument.name == name:
                            abi_type = argument.type

                    if not abi_type:
                        raise DecodingError(
                            f"'{name}' is not an indexed topic for event '{abi.name}'."
                        )

                    search_topics.append(arg)
                    abi_types.append(abi_type)

                encoded_topic_data = [
                    encode_single(topic_type, topic_data).hex()  # type: ignore
                    for topic_type, topic_data in zip(topics.types, search_topics)
                ]
                log_filter["topics"].extend(encoded_topic_data)
            else:
                log_filter["topics"] = event_parameters.pop("topics")

            log_result = [dict(log) for log in self._web3.eth.get_logs(log_filter)]  # type: ignore
            yield from self.network.ecosystem.decode_logs(abi, log_result)

    def send_transaction(self, txn: TransactionAPI) -> ReceiptAPI:
        txn_hash = self._web3.eth.send_raw_transaction(txn.serialize_transaction())
        req_confs = (
            txn.required_confirmations
            if txn.required_confirmations is not None
            else self.network.required_confirmations
        )

        receipt = self.get_transaction(txn_hash.hex(), required_confirmations=req_confs)
        logger.info(f"Confirmed {receipt.txn_hash} (gas_used={receipt.gas_used})")
        self._try_track_receipt(receipt)
        return receipt


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

    PROCESS_WAIT_TIMEOUT = 15
    process: Optional[Popen] = None
    is_stopping: bool = False

    @property
    @abstractmethod
    def process_name(self) -> str:
        """The name of the process, such as ``Hardhat node``."""

    @property
    @abstractmethod
    def is_connected(self) -> bool:
        """
        ``True`` if the process is running and connected.
        ``False`` otherwise.
        """

    @abstractmethod
    def build_command(self) -> List[str]:
        """
        Get the command as a list of ``str``.
        Subclasses should override and add command arguments if needed.

        Returns:
            List[str]: The command to pass to ``subprocess.Popen``.
        """

    def connect(self):
        """
        Start the process and connect to it.
        Subclasses handle the connection-related tasks.
        """

        if self.is_connected:
            raise ProviderError("Cannot connect twice. Call disconnect before connecting again.")

        # Register atexit handler to make sure disconnect is called for normal object lifecycle.
        atexit.register(self.disconnect)

        # Register handlers to ensure atexit handlers are called when Python dies.
        def _signal_handler(signum, frame):
            atexit._run_exitfuncs()
            sys.exit(143 if signum == SIGTERM else 130)

        signal(SIGINT, _signal_handler)
        signal(SIGTERM, _signal_handler)

    def disconnect(self):
        """Stop the process if it exists.
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
            self.process = _popen(*self.build_command(), preexec_fn=pre_exec_fn)

            with RPCTimeoutError(self, seconds=timeout) as _timeout:
                while True:
                    if self.is_connected:
                        break

                    time.sleep(0.1)
                    _timeout.check()

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
                self.process.send_signal(SIGINT)
                self._wait_for_popen(self.PROCESS_WAIT_TIMEOUT)
            except KeyboardInterrupt:
                logger.warning(warn_message)

        try:
            if self.process.poll() is None:
                _try_close(f"{warn_prefix}. Press Ctrl+C 1 more times to force quit")

            if self.process.poll() is None:
                self.process.kill()
                self._wait_for_popen(2)

        except KeyboardInterrupt:
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


pipe_kwargs = {"stdin": PIPE, "stdout": PIPE, "stderr": PIPE}


def _popen(*cmd, preexec_fn: Optional[Callable] = None) -> Popen:
    kwargs: Dict[str, Any] = {**pipe_kwargs}
    if preexec_fn:
        kwargs["preexec_fn"] = preexec_fn

    return Popen([str(c) for c in [*cmd]], **kwargs)


def _call(*args):
    return call([*args], **pipe_kwargs)


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
