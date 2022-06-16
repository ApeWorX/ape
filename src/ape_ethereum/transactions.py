import sys
from enum import Enum, IntEnum
from typing import IO, Dict, List, Optional, Union

from eth_abi import decode_abi
from eth_account import Account as EthAccount  # type: ignore
from eth_account._utils.legacy_transactions import (
    encode_transaction,
    serializable_unsigned_transaction_from_dict,
)
from eth_utils import keccak, to_int
from ethpm_types import HexBytes
from pydantic import BaseModel, Field, root_validator, validator
from rich.console import Console as RichConsole

from ape.api import ReceiptAPI, TransactionAPI
from ape.exceptions import OutOfGasError, SignatureError, TransactionError
from ape.utils import CallTraceParser, TraceStyles


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


class TransactionType(Enum):
    """
    Transaction enumerable type constants defined by
    `EIP-2718 <https://eips.ethereum.org/EIPS/eip-2718>`__.
    """

    STATIC = "0x00"
    ACCESS_LIST = "0x01"  # EIP-2930
    DYNAMIC = "0x02"  # EIP-1559


class AccessList(BaseModel):
    address: str
    storage_keys: List[Union[str, bytes, int]] = Field(default_factory=list, alias="storageKeys")


class BaseTransaction(TransactionAPI):
    def serialize_transaction(self) -> bytes:

        if not self.signature:
            raise SignatureError("The transaction is not signed.")

        txn_data = self.dict(exclude={"sender"})

        unsigned_txn = serializable_unsigned_transaction_from_dict(txn_data)
        signature = (self.signature.v, to_int(self.signature.r), to_int(self.signature.s))

        signed_txn = encode_transaction(unsigned_txn, signature)

        if self.sender and EthAccount.recover_transaction(signed_txn) != self.sender:
            raise SignatureError("Recovered signer doesn't match sender!")

        return signed_txn

    @property
    def txn_hash(self):
        return HexBytes(keccak(self.serialize_transaction()))


class StaticFeeTransaction(BaseTransaction):
    """
    Transactions that are pre-EIP-1559 and use the ``gasPrice`` field.
    """

    gas_price: Optional[int] = Field(None, alias="gasPrice")
    max_priority_fee: Optional[int] = Field(None, exclude=True)
    type: Union[str, int, bytes] = Field(TransactionType.STATIC.value, exclude=True)
    max_fee: Optional[int] = Field(None, exclude=True)

    @root_validator(pre=True)
    def calculate_read_only_max_fee(cls, values) -> Dict:
        # NOTE: Work-around, Pydantic doesn't handle calculated fields well.
        values["max_fee"] = values.get("gas_limit", 0) * values.get("gas_price", 0)
        return values


class DynamicFeeTransaction(BaseTransaction):
    """
    Transactions that are post-EIP-1559 and use the ``maxFeePerGas``
    and ``maxPriorityFeePerGas`` fields.
    """

    max_priority_fee: Optional[int] = Field(None, alias="maxPriorityFeePerGas")
    max_fee: Optional[int] = Field(None, alias="maxFeePerGas")
    type: Union[int, str, bytes] = Field(TransactionType.DYNAMIC.value)
    access_list: List[AccessList] = Field(default_factory=list, alias="accessList")

    @validator("type")
    def check_type(cls, value):

        if isinstance(value, TransactionType):
            return value.value

        return value


class AccessListTransaction(BaseTransaction):
    """
    EIP-2930 transactions are similar to legacy transaction with an added access list functionality.
    """

    gas_price: Optional[int] = Field(None, alias="gasPrice")
    type: Union[int, str, bytes] = Field(TransactionType.ACCESS_LIST.value)
    access_list: List[AccessList] = Field(default_factory=list, alias="accessList")

    @validator("type")
    def check_type(cls, value):

        if isinstance(value, TransactionType):
            return value.value

        return value


class Receipt(ReceiptAPI):
    gas_limit: int
    gas_price: int
    gas_used: int

    @property
    def ran_out_of_gas(self) -> bool:
        return (
            self.status == TransactionStatusEnum.FAILING.value and self.gas_used == self.gas_limit
        )

    @property
    def total_fees_paid(self) -> int:
        """
        The total amount of fees paid for the transaction.
        """
        return self.gas_used * self.gas_price

    @property
    def failed(self) -> bool:
        return self.status != TransactionStatusEnum.NO_ERROR

    def raise_for_status(self):
        if self.gas_limit is not None and self.ran_out_of_gas:
            raise OutOfGasError()
        elif self.status != TransactionStatusEnum.NO_ERROR:
            txn_hash = HexBytes(self.txn_hash).hex()
            raise TransactionError(message=f"Transaction '{txn_hash}' failed.")

    def show_trace(self, verbose: bool = False, file: IO[str] = sys.stdout):
        tree_factory = CallTraceParser(self, verbose=verbose)
        call_tree = self.provider.get_call_tree(self.txn_hash)
        root = tree_factory.parse_as_tree(call_tree)
        console = RichConsole(file=file)
        console.print(f"Call trace for [bold blue]'{self.txn_hash}'[/]")

        if call_tree.failed:
            default_message = "reverted without message"
            if not call_tree.returndata.hex().startswith(
                "0x08c379a00000000000000000000000000000000000000000000000000000000000000020"
            ):
                suffix = default_message
            else:
                decoded_result = decode_abi(("string",), call_tree.returndata[4:])
                if len(decoded_result) == 1:
                    suffix = f'reverted with message: "{decoded_result[0]}"'
                else:
                    suffix = default_message

            console.print(f"[bold red]{suffix}[/]")

        console.print(f"txn.origin=[{TraceStyles.CONTRACTS}]{self.sender}[/]")
        console.print(root)
