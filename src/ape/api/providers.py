import time
from enum import Enum, IntEnum
from pathlib import Path
from typing import Dict, Iterator, List, Optional

from dataclassy import as_dict
from eth_typing import HexStr
from eth_utils import add_0x_prefix
from hexbytes import HexBytes
from tqdm import tqdm  # type: ignore
from web3 import Web3

from ape.exceptions import TransactionError
from ape.logging import logger
from ape.types import BlockID, TransactionSignature
from ape.utils import abstractdataclass, abstractmethod

from . import networks
from .config import ConfigItem


class TransactionType(Enum):
    """
    Transaction enumerables type constants defined by
    `EIP-2718 <https://eips.ethereum.org/EIPS/eip-2718>`__.
    """

    STATIC = "0x0"
    DYNAMIC = "0x2"  # EIP-1559


@abstractdataclass
class TransactionAPI:
    """
    An API class representing a transaction.
    Ecosystem plugins implement one or more of transaction APIs
    depending on which schemas they permit,
    such as typed-transactions from `EIP-1559 <https://eips.ethereum.org/EIPS/eip-1559>`__.
    """

    chain_id: int = 0
    sender: str = ""
    receiver: str = ""
    nonce: Optional[int] = None  # NOTE: `Optional` only to denote using default behavior
    value: int = 0
    gas_limit: Optional[int] = None  # NOTE: `Optional` only to denote using default behavior
    data: bytes = b""
    type: TransactionType = TransactionType.STATIC

    # If left as None, will get set to the network's default required confirmations.
    required_confirmations: Optional[int] = None

    signature: Optional[TransactionSignature] = None

    @property
    def max_fee(self) -> int:
        """
        The total amount in fees willing to be spent on a transaction.
        Override this property as needed, such as for
        `EIP-1559 <https://eips.ethereum.org/EIPS/eip-1559>`__ differences.

        See :class:`~ape_ethereum.ecosystem.StaticFeeTransaction` and
        :class:`~ape_ethereum.ecosystem.DynamicFeeTransaction` as examples.

        Raises:
            NotImplementedError: When setting in a class that did not override the setter.

        Returns:
            int
        """
        return 0

    @max_fee.setter
    def max_fee(self, value: int):
        raise NotImplementedError("Max fee is not settable by default.")

    @property
    def total_transfer_value(self) -> int:
        """
        The total amount of WEI that a transaction could use.
        Useful for determining if an account balance can afford
        to submit the transaction.
        """
        return self.value + self.max_fee

    @abstractmethod
    def encode(self) -> bytes:
        """
        Take this object and produce a hash to sign to submit a transaction
        """

    def as_dict(self) -> dict:
        """
        Create a ``dict`` representation of the transaction.

        Returns:
            dict
        """
        return as_dict(self)

    def __repr__(self) -> str:
        data = as_dict(self)  # NOTE: `as_dict` could be overridden
        params = ", ".join(f"{k}={v}" for k, v in data.items())
        return f"<{self.__class__.__name__} {params}>"

    def __str__(self) -> str:
        data = as_dict(self)  # NOTE: `as_dict` could be overridden
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


@abstractdataclass
class ReceiptAPI:
    """
    An abstract class to represent a transaction receipt. The receipt
    contains information about the transaction, such as the status
    and required confirmations.

    **NOTE**: Use a ``required_confirmations`` of ``0`` in your transaction
    to not wait for confirmations.

    Get a receipt by making transactions in ``ape``, such as interacting with
    a :class:`ape.contracts.base.ContractInstance`.
    """

    provider: "ProviderAPI"
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
    nonce: int

    def __post_init__(self):
        txn_hash = self.txn_hash.hex() if isinstance(self.txn_hash, HexBytes) else self.txn_hash
        logger.info(f"Submitted {txn_hash} (gas_used={self.gas_used})")

    def __str__(self) -> str:
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

        Args:
            gas_limit (int): The gas limit of the transaction.

        Returns:
            bool:  ``True`` when the transaction failed and used the
            same amount of gas as the given ``gas_limit``.
        """
        return self.status == TransactionStatusEnum.FAILING and self.gas_used == self.gas_limit

    @classmethod
    @abstractmethod
    def decode(cls, data: dict) -> "ReceiptAPI":
        """
        Convert data to :class:`~ape.api.ReceiptAPI`.

        Args:
            data (dict): A dictionary of Receipt properties.

        Returns:
            :class:`~ape.api.ReceiptAPI`
        """

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

        confirmations_occurred = 0

        with ConfirmationsProgressBar(self.required_confirmations) as progress_bar:
            while confirmations_occurred < self.required_confirmations:
                latest_block = self.provider.get_block("latest")
                confirmations_occurred = latest_block.number - self.block_number  # type: ignore
                progress_bar.confs = confirmations_occurred

                if confirmations_occurred == self.required_confirmations:
                    break

                time.sleep(5)

        return self


@abstractdataclass
class BlockGasAPI:
    """
    An abstract class for representing gas data for a block.
    """

    gas_limit: int
    gas_used: int
    base_fee: Optional[int] = None

    @classmethod
    @abstractmethod
    def decode(cls, data: Dict) -> "BlockGasAPI":
        """
        Decode data to a :class:`~ape.api.BlockGasAPI`.

        Args:
            data (dict): A dictionary of block-gas properties.

        Returns:
            :class:`~ape.api.BlockGasAPI`
        """


@abstractdataclass
class BlockConsensusAPI:
    """
    An abstract class representing block consensus-data,
    such as PoW-related information regarding the block.
    `EIP-3675 <https://eips.ethereum.org/EIPS/eip-3675>`__.
    """

    difficulty: Optional[int] = None
    total_difficulty: Optional[int] = None

    @classmethod
    @abstractmethod
    def decode(cls, data: Dict) -> "BlockConsensusAPI":
        """
        Decode data to a :class:`~ape.api.BlockConsensusAPI`.

        Args:
            data (dict): A dictionary of data to decode.

        Returns:
            :class:`~ape.api.BlockConsensusAPI`
        """


@abstractdataclass
class BlockAPI:
    """
    An abstract class representing a block and its attributes.
    """

    gas_data: BlockGasAPI
    consensus_data: BlockConsensusAPI
    hash: HexBytes
    number: int
    parent_hash: HexBytes
    size: int
    timestamp: float

    @classmethod
    @abstractmethod
    def decode(cls, data: Dict) -> "BlockAPI":
        """
        Decode data to a :class:`~ape.api.BlockAPI`.

        Args:
            data (dict): A dictionary of data to decode.

        Returns:
            :class:`~ape.api.BlockAPI`
        """


@abstractdataclass
class ProviderAPI:
    """
    An abstraction of a connection to a network in an ecosystem. Example ``ProviderAPI``
    implementations include the `ape-infura <https://github.com/ApeWorX/ape-infura>`__
    plugin or the `ape-hardhat <https://github.com/ApeWorX/ape-hardhat>`__ plugin.
    """

    name: str
    """The name of the provider (should be the plugin name)."""

    network: networks.NetworkAPI
    """A reference to the network this provider provides."""

    config: ConfigItem
    """The provider's configuration."""

    provider_settings: dict
    """The settings for the provider, as overrides to the configuration."""

    data_folder: Path
    """The path to the  ``.ape`` directory."""

    request_header: str
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

        Returns:
            int: The value of the blockchain ID.
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
        The price for what it costs to transact.

        Returns:
            int
        """

    @property
    def priority_fee(self) -> int:
        """
        A miner tip to incentivize them
        to include your transaction in a block.

        Raises:
            NotImplementedError: When the provider does not implement
              `EIP-1559 <https://eips.ethereum.org/EIPS/eip-1559>`__ typed transactions.

        Returns:
            int: The value of the fee.
        """
        raise NotImplementedError("priority_fee is not implemented by this provider")

    @property
    def base_fee(self) -> int:
        """
        The minimum value required to get your transaction
        included on the next block.
        Only providers that implement `EIP-1559 <https://eips.ethereum.org/EIPS/eip-1559>`__
        will use this property.

        Raises:
            NotImplementedError: When this provider does not implement
              `EIP-1559 <https://eips.ethereum.org/EIPS/eip-1559>`__.

        Returns:
            int
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


class TestProviderAPI(ProviderAPI):
    """
    An API for providers that have development functionality, such as snapshotting.
    """

    @abstractmethod
    def snapshot(self) -> str:
        """
        Take a recording a state in a blockchain (for development only).

        Returns:
            str: The snapshot ID.
        """

    @abstractmethod
    def revert(self, snapshot_id: str):
        """
        Regress the current call using the given snapshot ID.
        Allows developers to go back to a previous state.

        Args:
            snapshot_ID (str): The snapshot ID.
        """


class Web3Provider(ProviderAPI):
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
        txn_dict = txn.as_dict()
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
        return self.network.ecosystem.block_class.decode(block_data)  # type: ignore

    def get_nonce(self, address: str) -> int:
        return self._web3.eth.get_transaction_count(address)  # type: ignore

    def get_balance(self, address: str) -> int:
        return self._web3.eth.get_balance(address)  # type: ignore

    def get_code(self, address: str) -> bytes:
        return self._web3.eth.get_code(address)  # type: ignore

    def send_call(self, txn: TransactionAPI) -> bytes:
        return self._web3.eth.call(txn.as_dict())

    def get_transaction(self, txn_hash: str, required_confirmations: int = 0) -> ReceiptAPI:
        if required_confirmations < 0:
            raise TransactionError(message="Required confirmations cannot be negative.")

        receipt_data = self._web3.eth.wait_for_transaction_receipt(HexBytes(txn_hash))
        txn = self._web3.eth.get_transaction(txn_hash)  # type: ignore
        receipt = self.network.ecosystem.receipt_class.decode(
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
        txn_hash = self._web3.eth.send_raw_transaction(txn.encode())
        req_confs = (
            txn.required_confirmations
            if txn.required_confirmations is not None
            else self.network.required_confirmations
        )
        receipt = self.get_transaction(txn_hash.hex(), required_confirmations=req_confs)
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

        Returns:
            str
        """
