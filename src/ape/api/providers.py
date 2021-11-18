from enum import Enum, IntEnum
from pathlib import Path
from typing import Iterator, List, Optional

from dataclassy import as_dict
from hexbytes import HexBytes
from web3 import Web3

from ape.exceptions import ProviderError
from ape.logging import logger
from ape.types import TransactionSignature

from . import networks
from .base import abstractdataclass, abstractmethod
from .config import ConfigItem


class TransactionType(Enum):
    STATIC = "0x0"
    DYNAMIC = "0x2"  # EIP-1559


@abstractdataclass
class TransactionAPI:
    chain_id: int = 0
    sender: str = ""
    receiver: str = ""
    nonce: Optional[int] = None  # NOTE: `Optional` only to denote using default behavior
    value: int = 0
    gas_limit: Optional[int] = None  # NOTE: `Optional` only to denote using default behavior
    data: bytes = b""
    type: TransactionType = TransactionType.STATIC

    signature: Optional[TransactionSignature] = None

    def __post_init__(self):
        if not self.is_valid:
            raise ProviderError("Transaction is not valid.")

    @property
    def max_fee(self) -> int:
        """
        The total amount in fees willing to be spent on a transaction.
        Override this property as needed, such as for EIP-1559 differences.

        See :class:`~ape_ethereum.ecosystem.StaticFeeTransaction` and
        :class`~ape_ethereum.ecosystem.DynamicFeeTransaction` as examples.
        """
        return 0

    @max_fee.setter
    def max_fee(self, value):
        raise NotImplementedError("Max fee is not settable by default.")

    @property
    def total_transfer_value(self) -> int:
        """
        The total amount of WEI that a transaction could use.
        Useful for determining if an account balance can afford
        to submit the transaction.
        """
        return self.value + self.max_fee

    @property
    @abstractmethod
    def is_valid(self):
        ...

    @abstractmethod
    def encode(self) -> bytes:
        """
        Take this object and produce a hash to sign to submit a transaction
        """

    def as_dict(self) -> dict:
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
    FAILING = 0
    NO_ERROR = 1


@abstractdataclass
class ReceiptAPI:
    txn_hash: str
    status: TransactionStatusEnum
    block_number: int
    gas_used: int
    gas_price: int
    logs: List[dict] = []
    contract_address: Optional[str] = None

    def __post_init__(self):
        txn_hash = self.txn_hash.hex() if isinstance(self.txn_hash, HexBytes) else self.txn_hash
        logger.info(f"Submitted {txn_hash} (gas_used={self.gas_used})")

    def __str__(self) -> str:
        return f"<{self.__class__.__name__} {self.txn_hash}>"

    def raise_for_status(self, txn: TransactionAPI):
        """
        Handle provider-specific errors regarding a non-successful
        :class:`~api.providers.TransactionStatusEnum`.
        """

    def ran_out_of_gas(self, gas_limit: int) -> bool:
        """
        Returns ``True`` when the transaction failed and used the
        same amount of gas as the given ``gas_limit``.
        """
        return self.status == TransactionStatusEnum.FAILING and self.gas_used == gas_limit

    @classmethod
    @abstractmethod
    def decode(cls, data: dict) -> "ReceiptAPI":
        ...


@abstractdataclass
class ProviderAPI:
    """
    A Provider must work with a particular Network in a particular Ecosystem
    """

    name: str  # Plugin name
    network: networks.NetworkAPI
    config: ConfigItem
    provider_settings: dict
    data_folder: Path
    request_header: str

    @abstractmethod
    def connect(self):
        ...

    @abstractmethod
    def disconnect(self):
        ...

    @abstractmethod
    def update_settings(self, new_settings: dict):
        ...

    @property
    @abstractmethod
    def chain_id(self) -> int:
        ...

    @abstractmethod
    def get_balance(self, address: str) -> int:
        ...

    @abstractmethod
    def get_code(self, address: str) -> bytes:
        ...

    @abstractmethod
    def get_nonce(self, address: str) -> int:
        ...

    @abstractmethod
    def estimate_gas_cost(self, txn: TransactionAPI) -> int:
        ...

    @property
    @abstractmethod
    def gas_price(self) -> int:
        ...

    @property
    @abstractmethod
    def priority_fee(self) -> int:
        raise NotImplementedError("priority_fee is not implemented by this provider")

    @property
    @abstractmethod
    def base_fee(self) -> int:
        raise NotImplementedError("base_fee is not implemented by this provider")

    @abstractmethod
    def send_call(self, txn: TransactionAPI) -> bytes:  # Return value of function
        ...

    @abstractmethod
    def get_transaction(self, txn_hash: str) -> ReceiptAPI:
        ...

    @abstractmethod
    def send_transaction(self, txn: TransactionAPI) -> ReceiptAPI:
        ...

    @abstractmethod
    def get_events(self, **filter_params) -> Iterator[dict]:
        ...


class TestProviderAPI(ProviderAPI):
    """
    An API for providers that have development functionality, such as snapshotting.
    """

    @abstractmethod
    def snapshot(self) -> str:
        ...

    @abstractmethod
    def revert(self, snapshot_id: str):
        ...


class Web3Provider(ProviderAPI):
    """
    A base provider that is web3 based.
    """

    _web3: Web3 = None  # type: ignore

    def update_settings(self, new_settings: dict):
        """
        Update the provider settings and re-connect.
        """
        self.disconnect()
        self.provider_settings.update(new_settings)
        self.connect()

    def estimate_gas_cost(self, txn: TransactionAPI) -> int:
        """
        Generates and returns an estimate of how much gas is necessary
        to allow the transaction to complete.
        The transaction will not be added to the blockchain.
        """
        txn_dict = txn.as_dict()
        return self._web3.eth.estimate_gas(txn_dict)  # type: ignore

    @property
    def chain_id(self) -> int:
        """
        Returns the currently configured chain ID,
        a value used in replay-protected transaction signing as introduced by EIP-155.
        """
        return self._web3.eth.chain_id

    @property
    def gas_price(self) -> int:
        """
        Returns the current price per gas in wei.
        """
        return self._web3.eth.generate_gas_price()  # type: ignore

    @property
    def priority_fee(self) -> int:
        """
        Returns the current max priority fee per gas in wei.
        """
        return self._web3.eth.max_priority_fee

    @property
    def base_fee(self) -> int:
        block = self._web3.eth.get_block("latest")
        return block.baseFeePerGas  # type: ignore

    def get_nonce(self, address: str) -> int:
        """
        Returns the number of transactions sent from an address.
        """
        return self._web3.eth.get_transaction_count(address)  # type: ignore

    def get_balance(self, address: str) -> int:
        """
        Returns the balance of the account of a given address.
        """
        return self._web3.eth.get_balance(address)  # type: ignore

    def get_code(self, address: str) -> bytes:
        """
        Returns code at a given address.
        """
        return self._web3.eth.get_code(address)  # type: ignore

    def send_call(self, txn: TransactionAPI) -> bytes:
        """
        Executes a new message call immediately without creating a
        transaction on the block chain.
        """
        return self._web3.eth.call(txn.as_dict())

    def get_transaction(self, txn_hash: str) -> ReceiptAPI:
        """
        Returns the information about a transaction requested by transaction hash.
        """
        # TODO: Work on API that let's you work with ReceiptAPI and re-send transactions
        receipt = self._web3.eth.wait_for_transaction_receipt(txn_hash)  # type: ignore
        txn = self._web3.eth.get_transaction(txn_hash)  # type: ignore
        return self.network.ecosystem.receipt_class.decode({**txn, **receipt})

    def get_events(self, **filter_params) -> Iterator[dict]:
        """
        Returns an array of all logs matching a given set of filter parameters.
        """
        return iter(self._web3.eth.get_logs(filter_params))  # type: ignore

    def send_transaction(self, txn: TransactionAPI) -> ReceiptAPI:
        txn_hash = self._web3.eth.send_raw_transaction(txn.encode())
        receipt = self.get_transaction(txn_hash.hex())
        return receipt
