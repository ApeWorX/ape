import sys
from enum import Enum, IntEnum
from functools import cached_property
from typing import IO, TYPE_CHECKING, Any, Optional, Union, List, Dict

from eth_abi import decode
from eth_account import Account as EthAccount
from eth_account._utils.legacy_transactions import (
    encode_transaction,
    serializable_unsigned_transaction_from_dict,
)
from eth_pydantic_types import HexBytes
from eth_utils import decode_hex, encode_hex, keccak, to_canonical_address, to_int
from ethpm_types.abi import EventABI, MethodABI
from pydantic import BaseModel, Field, field_serializer, field_validator, model_validator

from ape.api.transactions import ReceiptAPI, TransactionAPI
from ape.exceptions import OutOfGasError, SignatureError, TransactionError
from ape.logging import logger
from ape.types.address import AddressType
from ape.types.basic import HexInt
from ape.types.events import ContractLog, ContractLogContainer
from ape.types.signatures import MessageSignature
from ape.types.trace import SourceTraceback
from ape.utils.misc import ZERO_ADDRESS
from ape_ethereum.trace import Trace, _events_to_trees

if TYPE_CHECKING:
    from ethpm_types import ContractType
    from typing_extensions import Self
    from ape.contracts import ContractEvent


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

    STATIC = 0
    ACCESS_LIST = 1  # EIP-2930
    DYNAMIC = 2  # EIP-1559
    SHARED_BLOB = 3  # EIP-4844
    SET_CODE = 4  # EIP-7702


class AccessList(BaseModel):
    address: AddressType
    storage_keys: List[HexBytes] = Field(default_factory=list, alias="storageKeys")


class Authorization(BaseModel):
    """
    `EIP-7702 <https://eips.ethereum.org/EIPS/eip-7702>`__ authorization list item.
    """

    chain_id: HexInt = Field(alias="chainId")
    address: AddressType
    nonce: HexInt
    v: HexInt = Field(alias="yParity")
    r: HexBytes
    s: HexBytes

    @field_serializer("chain_id", "nonce", "v")
    def _int_to_hex(self, value: int) -> str:
        return to_hex(value)

    @classmethod
    def from_signature(cls, chain_id: int, address: AddressType, nonce: int, signature: MessageSignature) -> "Self":
        return cls(chainId=chain_id, address=address, nonce=nonce, yParity=signature.v, r=signature.r, s=signature.s)

    @property
    def signature(self) -> MessageSignature:
        return MessageSignature(v=self.v, r=self.r, s=self.s)

    @cached_property
    def authority(self) -> AddressType:
        # TODO: Move above when `web3` pin is `>7`
        from eth_account.typed_transactions.set_code_transaction import Authorization as EthAcctAuth

        auth = EthAcctAuth(self.chain_id, to_canonical_address(self.address), self.nonce)
        return EthAccount._recover_hash(auth.hash(), vrs=(self.signature.v, to_int(self.r), to_int(self.s)))


class BaseTransaction(TransactionAPI):
    def serialize_transaction(self) -> bytes:
        if not self.signature:
            message = "The transaction is not signed."
            if not self.sender:
                message = (
                    f"{message} "
                    "Did you forget to add the `sender=` kwarg to the transaction function call?"
                )
            raise SignatureError(message, transaction=self)

        txn_data = self.model_dump(by_alias=True, exclude={"sender", "type"})

        if txn_data.get("to") == ZERO_ADDRESS:
            txn_data.pop("to")

        txn_data = self._normalize_lists(txn_data)

        unsigned_txn = serializable_unsigned_transaction_from_dict(txn_data)
        signature = (self.signature.v, to_int(self.signature.r), to_int(self.signature.s))
        signed_txn = encode_transaction(unsigned_txn, signature)

        self._verify_signature(signed_txn)

        return signed_txn

    def _normalize_lists(self, txn_data: dict) -> dict:
        def _normalize_hex_list(lst: List[dict], keys: Optional[List[str]] = None) -> List[dict]:
            keys = keys or []
            normalized = []
            for item in lst:
                normalized.append({k: to_hex(v) if isinstance(v, bytes) or k in keys else v for k, v in item.items()})
            return normalized

        if "accessList" in txn_data:
            txn_data["accessList"] = [
                {**item, "storageKeys": [to_hex(k) for k in item.get("storageKeys", [])]} for item in txn_data["accessList"]
            ]

        if "authorizationList" in txn_data:
            txn_data["authorizationList"] = _normalize_hex_list(txn_data["authorizationList"], keys=["r", "s"])

        return txn_data

    def _verify_signature(self, signed_txn: bytes):
        impersonated_accounts = self.account_manager.test_accounts._impersonated_accounts
        if self.sender and self.sender not in impersonated_accounts:
            recovered_signer = EthAccount.recover_transaction(signed_txn)
            if recovered_signer != self.sender:
                raise SignatureError(
                    f"Recovered signer '{recovered_signer}' doesn't match sender {self.sender}!",
                    transaction=self,
                )

    @property
    def txn_hash(self) -> HexBytes:
        txn_bytes = self.serialize_transaction()
        return HexBytes(keccak(txn_bytes))


class StaticFeeTransaction(BaseTransaction):
    """
    Transactions that are pre-EIP-1559 and use the ``gasPrice`` field.
    """

    gas_price: Optional[HexInt] = Field(default=None, alias="gasPrice")
    max_priority_fee: Optional[HexInt] = Field(default=None, exclude=True)  # type: ignore
    type: HexInt = Field(default=TransactionType.STATIC.value, exclude=True)
    max_fee: Optional[HexInt] = Field(default=None, exclude=True)  # type: ignore

    @model_validator(mode="after")
    @classmethod
    def calculate_read_only_max_fee(cls, tx):
        # Work-around: we cannot use a computed field to override a non-computed field.
        tx.max_fee = (tx.gas_limit or 0) * (tx.gas_price or 0)
        return tx


class AccessListTransaction(StaticFeeTransaction):
    """
    `EIP-2930 <https://eips.ethereum.org/EIPS/eip-2930>`__
    transactions are similar to legacy transaction with an added access list functionality.
    """

    gas_price: Optional[int] = Field(default=None, alias="gasPrice")
    type: int = TransactionType.ACCESS_LIST.value
    access_list: List[AccessList] = Field(default_factory=list, alias="accessList")

    @field_validator("type")
    @classmethod
    def check_type(cls, value):
        return value.value if isinstance(value, TransactionType) else value


class DynamicFeeTransaction(BaseTransaction):
    """
    Transactions that are post-EIP-1559 and use the ``maxFeePerGas``
    and ``maxPriorityFeePerGas`` fields.
    """

    max_priority_fee: Optional[HexInt] = Field(default=None, alias="maxPriorityFeePerGas")
    max_fee: Optional[HexInt] = Field(default=None, alias="maxFeePerGas")
    type: HexInt = TransactionType.DYNAMIC.value
    access_list: List[AccessList] = Field(default_factory=list, alias="accessList")

    @field_validator("type")
    @classmethod
    def check_type(cls, value):
        return value.value if isinstance(value, TransactionType) else value


class SharedBlobTransaction(DynamicFeeTransaction):
    """
    `EIP-4844 <https://eips.ethereum.org/EIPS/eip-4844>`__ transactions.
    """

    max_fee_per_blob_gas: HexInt = Field(default=0, alias="maxFeePerBlobGas")
    blob_versioned_hashes: List[HexBytes] = Field(default_factory=list, alias="blobVersionedHashes")

    receiver: AddressType = Field(default=ZERO_ADDRESS, alias="to")
    """
    Overridden because EIP-4844 states it cannot be nil.
    """


class SetCodeTransaction(DynamicFeeTransaction):
    """
    `EIP-7702 <https://eips.ethereum.org/EIPS/eip-7702>`__ transactions.
    """

    authorizations: List[Authorization] = Field(default_factory=list, alias="authorizationList")
    receiver: AddressType = Field(default=ZERO_ADDRESS, alias="to")
    """
    Overridden because EIP-7702 states it cannot be nil.
    """


class Receipt(ReceiptAPI):
    gas_limit: HexInt
    gas_price: HexInt
    gas_used: HexInt

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

    @cached_property
    def debug_logs_typed(self) -> List[tuple]:
        """
        Extract messages to console outputted by contracts via print() or console.log() statements
        """
        try:
            trace = self.trace
        # Some providers do not implement this, so skip.
        except NotImplementedError:
            logger.debug("Call tree not available, skipping debug log extraction")
            return []

        if trace is None or not isinstance(trace, Trace):
            return []

        return list(trace.debug_logs)

    @cached_property
    def contract_type(self) -> Optional["ContractType"]:
        if address := (self.receiver or self.contract_address):
            return self.chain_manager.contracts.get(address)
        return None

    @cached_property
    def method_called(self) -> Optional[MethodABI]:
        if not self.contract_type:
            return None
        method_id = self.data[:4]
        return self.contract_type.methods.get(method_id)

    @cached_property
    def source_traceback(self) -> SourceTraceback:
        if contract_type := self.contract_type:
            if contract_src := self.local_project._create_contract_source(contract_type):
                try:
                    return SourceTraceback.create(contract_src, self.trace, HexBytes(self.data))
                except Exception as err:
                    logger.error(f"Problem retrieving traceback: {err}")
        return SourceTraceback.model_validate([])

    def raise_for_status(self):
        err: Optional[TransactionError] = None
        if self.gas_limit is not None and self.ran_out_of_gas:
            err = OutOfGasError(txn=self)
        elif self.status != TransactionStatusEnum.NO_ERROR:
            txn_hash = self.txn_hash
            err = TransactionError(f"Transaction '{txn_hash}' failed.", txn=self)

        if err:
            self.error = err
            if err and self.transaction.raise_on_revert:
                raise err

    def show_trace(self, verbose: bool = False, file: IO[str] = sys.stdout):
        self.trace.show(verbose=verbose, file=file)

    def show_gas_report(self, file: IO[str] = sys.stdout):
        self.trace.show_gas_report(file=file)

    def show_source_traceback(self, file: IO[str] = sys.stdout):
        self.chain_manager._reports.show_source_traceback(
            self.source_traceback, file=file, failing=self.failed
        )

    def show_events(self, file: IO[str] = sys.stdout):
        if provider := self.network_manager.active_provider:
            ecosystem = provider.network.ecosystem
        else:
            ecosystem = self.network_manager.ethereum

        enriched_events = ecosystem._enrich_trace_events(self.logs)
        event_trees = _events_to_trees(enriched_events)
        self.chain_manager._reports.show_events(event_trees, file=file)

    def decode_logs(
        self,
        abi: Optional[
            Union[List[Union[EventABI, "ContractEvent"]], Union[EventABI, "ContractEvent"]]
        ] = None,
    ) -> ContractLogContainer:
        if not self.logs:
            return ContractLogContainer([])

        if abi is not None:
            if not isinstance(abi, (list, tuple)):
                abi = [abi]
            event_abis = [a.abi if not isinstance(a, EventABI) else a for a in abi]
            return ContractLogContainer(
                self.provider.network.ecosystem.decode_logs(self.logs, *event_abis)
            )

        addresses = {x["address"] for x in self.logs}
        contract_types = self.chain_manager.contracts.get_multiple(addresses)
        selectors = {
            address.lower(): {
                encode_hex(keccak(text=abi.selector)): abi for abi in contract.events
            }
            for address, contract in contract_types.items()
        }

        decoded_logs: ContractLogContainer = ContractLogContainer()
        for log in self.logs:
            decoded = self._decode_single_log(log, selectors)
            decoded_logs.extend(decoded if isinstance(decoded, list) else [decoded])

        return decoded_logs

    def _decode_single_log(self, log: dict, selectors: dict) -> Optional[ContractLog]:
        if library_log := self._decode_ds_note(log):
            return library_log

        lower_address = log.get("address", "").lower()
        if lower_address in selectors and (topics := log.get("topics")):
            selector = encode_hex(topics[0])
            if selector in selectors[lower_address]:
                return self.provider.network.ecosystem.decode_logs([log], selectors[lower_address][selector])

        return self._default_log(log)

    def _decode_ds_note(self, log: dict) -> Optional[ContractLog]:
        if len(log.get("topics", [])) == 0:
            return None

        selector, tail = log["topics"][0][:4], log["topics"][0][4:]
        if any(tail) or not (contract_type := self.chain_manager.contracts.get(log["address"])):
            return None

        method_abi = contract_type.mutable_methods.get(selector)
        if not method_abi:
            return None

        data = decode_hex(log["data"]) if isinstance(log["data"], str) else log["data"]
        input_types = [i.canonical_type for i in method_abi.inputs]
        values = decode(input_types, data[4:])
        address = self.provider.network.ecosystem.decode_address(log["address"])

        return ContractLog(
            block_hash=log["blockHash"],
            block_number=log["blockNumber"],
            contract_address=address,
            event_arguments={i.name: value for i, value in zip(method_abi.inputs, values)},
            event_name=method_abi.name,
            log_index=log["logIndex"],
            transaction_hash=log["transactionHash"],
            transaction_index=log["transactionIndex"],
        )


class SharedBlobReceipt(Receipt):
    """
    An `EIP-4844 <https://eips.ethereum.org/EIPS/eip-4844#blob-transaction>`__"
    blob transaction.
    """

    blob_gas_used: Optional[HexInt] = Field(default=None, alias="blobGasUsed")
    """
    The total amount of blob gas consumed by the transactions within the block.
    """

    blob_gas_price: HexInt = Field(alias="blobGasPrice")
    """
    The blob-gas price, independent from regular gas price.
    """
