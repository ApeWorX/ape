from enum import Enum, IntEnum
from typing import Dict, Optional, Union

from eth_account import Account as EthAccount  # type: ignore
from eth_account._utils.legacy_transactions import (
    encode_transaction,
    serializable_unsigned_transaction_from_dict,
)
from eth_utils import to_int
from hexbytes import HexBytes
from pydantic import Field, root_validator, validator

from ape.api import ReceiptAPI, TransactionAPI
from ape.exceptions import OutOfGasError, SignatureError, TransactionError


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
    DYNAMIC = "0x02"  # EIP-1559


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

    @validator("type")
    def check_type(cls, value):

        if isinstance(value, TransactionType):
            return value.value

        return value


class Receipt(ReceiptAPI):
    def raise_for_status(self):
        if self.gas_limit is not None and self.ran_out_of_gas:
            raise OutOfGasError()
        elif self.status != TransactionStatusEnum.NO_ERROR:
            txn_hash = HexBytes(self.txn_hash).hex()
            raise TransactionError(message=f"Transaction '{txn_hash}' failed.")

    @property
    def ran_out_of_gas(self) -> bool:
        return (
            self.status == TransactionStatusEnum.FAILING.value and self.gas_used == self.gas_limit
        )
