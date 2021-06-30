from enum import IntEnum
from pathlib import Path
from typing import Iterator, List, Optional

from dataclassy import as_dict

from ape.utils import notify

from . import networks
from .base import abstractdataclass, abstractmethod


@abstractdataclass
class TransactionAPI:
    chain_id: int = 0
    sender: str = ""
    receiver: str = ""
    nonce: int = 0
    value: int = 0
    gas_limit: int = 0
    gas_price: int = 0
    data: bytes = b""

    signature: bytes = b""

    def __post_init__(self):
        if not self.is_valid:
            raise Exception("Transaction is not valid!")

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
        data = as_dict(self)  # NOTE: `as_dict` could be overriden
        params = ", ".join(f"{k}={v}" for k, v in data.items())
        return f"<{self.__class__.__name__} {params}>"

    def __str__(self) -> str:
        data = as_dict(self)  # NOTE: `as_dict` could be overriden
        if len(data["data"]) > 9:
            data["data"] = (
                "0x" + bytes(data["data"][:3]).hex() + "..." + bytes(data["data"][-3:]).hex()
            )
        else:
            data["data"] = "0x" + bytes(data["data"]).hex()
        params = "\n  ".join(f"{k}: {v}" for k, v in data.items())
        return f"{self.__class__.__name__}:\n  {params}"


class TransactionStatusEnum(IntEnum):
    failing = 0
    no_error = 1


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
        notify("INFO", f"Submitted {self.txn_hash.hex()}")

    def __str__(self) -> str:
        return f"<{self.__class__.__name__} {self.txn_hash}>"

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
    config: dict
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
