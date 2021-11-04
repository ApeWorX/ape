from enum import IntEnum
from pathlib import Path
from typing import Iterator, List, Optional

from dataclassy import as_dict
from hexbytes import HexBytes

from ape.logging import logger
from ape.types import TransactionSignature

from ..exceptions import ProviderError
from . import networks
from .base import abstractdataclass, abstractmethod
from .config import ConfigItem


@abstractdataclass
class TransactionAPI:
    chain_id: int = 0
    sender: str = ""
    receiver: str = ""
    nonce: Optional[int] = None  # NOTE: `Optional` only to denote using default behavior
    value: int = 0
    gas_limit: Optional[int] = None  # NOTE: `Optional` only to denote using default behavior
    gas_price: Optional[int] = None  # NOTE: `Optional` only to denote using default behavior
    data: bytes = b""

    signature: Optional[TransactionSignature] = None

    def __post_init__(self):
        if not self.is_valid:
            raise ProviderError("Transaction is not valid.")

    @property
    def total_transfer_value(self) -> int:
        """
        The total amount of WEI that a transaction could use.
        Useful for determining if an account balance can afford
        to submit the transaction.
        """
        # TODO Support EIP-1559
        return (self.gas_limit or 0) * (self.gas_price or 0) + self.value

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
