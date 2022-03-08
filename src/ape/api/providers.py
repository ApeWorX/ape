import atexit
import ctypes
import platform
import shutil
import sys
import time
from abc import ABC
from enum import Enum, IntEnum
from pathlib import Path
from signal import SIGINT, SIGTERM, signal
from subprocess import PIPE, Popen, call
from typing import TYPE_CHECKING, Any, Callable, Dict, Iterator, List, Optional

from eth_typing import HexStr
from eth_utils import add_0x_prefix
from hexbytes import HexBytes
from pydantic import Field, validator
from tqdm import tqdm  # type: ignore
from web3 import Web3

from ape.api.config import PluginConfig
from ape.api.networks import NetworkAPI
from ape.exceptions import (
    ProviderError,
    RPCTimeoutError,
    SubprocessError,
    SubprocessTimeoutError,
    TransactionError,
)
from ape.logging import logger
from ape.types import BlockID, SnapshotID, TransactionSignature
from ape.utils import BaseInterfaceModel, abstractmethod, cached_property

if TYPE_CHECKING:
    from ape.api.explorers import ExplorerAPI


def raises_not_implemented(fn):
    def inner(*args, **kwargs):
        raise NotImplementedError(
            f"Attempted to call method '{fn.__name__}' in 'ProviderAPI', "
            f"which is only available in 'TestProviderAPI'."
        )

    return inner


class TransactionType(Enum):
    """
    Transaction enumerables type constants defined by
    `EIP-2718 <https://eips.ethereum.org/EIPS/eip-2718>`__.
    """

    STATIC = "0x00"
    DYNAMIC = "0x02"  # EIP-1559


class TransactionAPI(BaseInterfaceModel):
    """
    An API class representing a transaction.
    Ecosystem plugins implement one or more of transaction APIs
    depending on which schemas they permit,
    such as typed-transactions from `EIP-1559 <https://eips.ethereum.org/EIPS/eip-1559>`__.
    """

    chain_id: int = Field(0, alias="chainId")
    receiver: Optional[str] = Field(None, alias="to")
    sender: Optional[str] = Field(None, alias="from")
    gas_limit: Optional[int] = Field(None, alias="gas")
    nonce: Optional[int] = None  # NOTE: `Optional` only to denote using default behavior
    value: int = 0
    data: bytes = b""
    type: TransactionType = TransactionType.STATIC
    max_fee: Optional[int] = None
    max_priority_fee: Optional[int] = None

    # If left as None, will get set to the network's default required confirmations.
    required_confirmations: Optional[int] = Field(None, exclude=True)

    signature: Optional[TransactionSignature] = Field(exclude=True)

    class Config:
        allow_population_by_field_name = True

    @property
    def total_transfer_value(self) -> int:
        """
        The total amount of WEI that a transaction could use.
        Useful for determining if an account balance can afford
        to submit the transaction.
        """
        if self.max_fee is None:
            raise TransactionError(message="Max fee must not be null.")

        return self.value + self.max_fee

    @abstractmethod
    def serialize_transaction(self) -> bytes:
        """
        Serialize the transaction
        """

    def __repr__(self) -> str:
        data = self.dict()
        params = ", ".join(f"{k}={v}" for k, v in data.items())
        return f"<{self.__class__.__name__} {params}>"

    def __str__(self) -> str:
        data = self.dict()
        if len(data["data"]) > 9:
            data["data"] = (
                "0x" + bytes(data["data"][:3]).hex() + "..." + bytes(data["data"][-3:]).hex()
            )
        else:
            data["data"] = "0x" + bytes(data["data"]).hex()
        params = "\n  ".join(f"{k}: {v}" for k, v in data.items())
        return f"{self.__class__.__name__}:\n  {params}"


class TransactionStatusEnum(IntEnum):
    """
    An ``Enum`` class representing the status of a transaction.
    """

    FAILING = 0
    """The transaction has failed or is in the process of failing."""

    NO_ERROR = 1
    """
    The transaction is successful and is confirmed or is in the process
    of getting confirmed.
    """


class ConfirmationsProgressBar:
    """
    A progress bar tracking the confirmations of a transaction.
    """

    def __init__(self, confirmations: int):
        self._req_confs = confirmations
        self._bar = tqdm(range(confirmations))
        self._confs = 0

    def __enter__(self):
        self._update_bar(0)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self._bar.close()

    @property
    def confs(self) -> int:
        """
        The number of confirmations that have occurred.

        Returns:
            int: The total number of confirmations that have occurred.
        """
        return self._confs

    @confs.setter
    def confs(self, new_value):
        if new_value == self._confs:
            return

        diff = new_value - self._confs
        self._confs = new_value
        self._update_bar(diff)

    def _update_bar(self, amount: int):
        self._set_description()
        self._bar.update(amount)
        self._bar.refresh()

    def _set_description(self):
        self._bar.set_description(f"Confirmations ({self._confs}/{self._req_confs})")


class ReceiptAPI(BaseInterfaceModel):
    """
    An abstract class to represent a transaction receipt. The receipt
    contains information about the transaction, such as the status
    and required confirmations.

    **NOTE**: Use a ``required_confirmations`` of ``0`` in your transaction
    to not wait for confirmations.

    Get a receipt by making transactions in ``ape``, such as interacting with
    a :class:`ape.contracts.base.ContractInstance`.
    """

    txn_hash: str
    status: TransactionStatusEnum
    block_number: int
    gas_used: int
    gas_price: int
    gas_limit: int
    logs: List[dict] = []
    contract_address: Optional[str] = None
    required_confirmations: int = 0
    sender: str
    receiver: str
    nonce: Optional[int] = None

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} {self.txn_hash}>"

    def raise_for_status(self):
        """
        Handle provider-specific errors regarding a non-successful
        :class:`~api.providers.TransactionStatusEnum`.
        """

    @property
    def ran_out_of_gas(self) -> bool:
        """
        Check if a transaction has ran out of gas and failed.

        Returns:
            bool:  ``True`` when the transaction failed and used the
            same amount of gas as the given ``gas_limit``.
        """
        return self.status == TransactionStatusEnum.FAILING and self.gas_used == self.gas_limit

    @property
    def _explorer(self) -> Optional["ExplorerAPI"]:
        return self.provider.network.explorer

    @property
    def _block_time(self) -> int:
        return self.provider.network.block_time

    @property
    def _confirmations_occurred(self) -> int:
        latest_block = self.provider.get_block("latest")

        if latest_block.number is None:
            return 0

        return latest_block.number - self.block_number

    def await_confirmations(self) -> "ReceiptAPI":
        """
        Wait for a transaction to be considered confirmed.

        Returns:
            :class:`~ape.api.ReceiptAPI`: The receipt that is now confirmed.
        """
        # Wait for nonce from provider to increment.
        sender_nonce = self.provider.get_nonce(self.sender)
        while sender_nonce == self.nonce:  # type: ignore
            time.sleep(1)
            sender_nonce = self.provider.get_nonce(self.sender)

        if self.required_confirmations == 0:
            # The transaction might not yet be confirmed but
            # the user is aware of this. Or, this is a development environment.
            return self

        confirmations_occurred = self._confirmations_occurred
        if confirmations_occurred >= self.required_confirmations:
            return self

        # If we get here, that means the transaction has been recently submitted.
        log_message = f"Submitted {self.txn_hash}"
        if self._explorer:
            explorer_url = self._explorer.get_transaction_url(self.txn_hash)
            if explorer_url:
                log_message = f"{log_message}\n{self._explorer.name} URL: {explorer_url}"

        logger.info(log_message)

        with ConfirmationsProgressBar(self.required_confirmations) as progress_bar:
            while confirmations_occurred < self.required_confirmations:
                confirmations_occurred = self._confirmations_occurred
                progress_bar.confs = confirmations_occurred

                if confirmations_occurred == self.required_confirmations:
                    break

                time_to_sleep = int(self._block_time / 2)
                time.sleep(time_to_sleep)

        return self


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
    def get_events(self, **filter_params) -> Iterator[dict]:
        """
        Get all logs matching a given set of filter parameters.

        Args:
            `filter_params`: Filter which logs you get.

        Returns:
            Iterator[dict]: A dictionary of events.
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
        return self._web3.eth.chain_id

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

    def get_events(self, **filter_params) -> Iterator[dict]:
        return iter(self._web3.eth.get_logs(filter_params))  # type: ignore

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
