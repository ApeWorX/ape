import sys
from enum import Enum, IntEnum
from functools import cached_property
from typing import IO, Any, Optional, Union

from eth_abi import decode
from eth_account import Account as EthAccount
from eth_account._utils.legacy_transactions import (
    encode_transaction,
    serializable_unsigned_transaction_from_dict,
)
from eth_pydantic_types import HexBytes
from eth_utils import decode_hex, encode_hex, keccak, to_hex, to_int
from ethpm_types import ContractType
from ethpm_types.abi import EventABI, MethodABI
from pydantic import BaseModel, Field, field_validator, model_validator

from ape.api.transactions import ReceiptAPI, TransactionAPI
from ape.contracts import ContractEvent
from ape.exceptions import OutOfGasError, SignatureError, TransactionError
from ape.logging import logger
from ape.types.address import AddressType
from ape.types.basic import HexInt
from ape.types.events import ContractLog, ContractLogContainer
from ape.types.trace import SourceTraceback
from ape.utils.misc import ZERO_ADDRESS
from ape_ethereum.trace import Trace, _events_to_trees


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


class AccessList(BaseModel):
    address: AddressType
    storage_keys: list[HexBytes] = Field(default_factory=list, alias="storageKeys")


class BaseTransaction(TransactionAPI):
    def serialize_transaction(self) -> bytes:
        if not self.signature:
            message = "The transaction is not signed."
            if not self.sender:
                message = (
                    f"{message} "
                    "Did you forget to add the `sender=` kwarg to the transaction function call?"
                )

            raise SignatureError(message)

        txn_data = self.model_dump(by_alias=True, exclude={"sender", "type"})

        # This messes up the signature
        if txn_data.get("to") == ZERO_ADDRESS:
            del txn_data["to"]

        # Adjust bytes in the access list if necessary.
        if "accessList" in txn_data:
            adjusted_access_list = []

            for item in txn_data["accessList"]:
                adjusted_item = {**item}
                storage_keys_corrected = [
                    to_hex(k) if isinstance(k, bytes) else k for k in item.get("storageKeys", [])
                ]

                if storage_keys_corrected:
                    adjusted_item["storageKeys"] = storage_keys_corrected

                adjusted_access_list.append(adjusted_item)

            txn_data["accessList"] = adjusted_access_list

        unsigned_txn = serializable_unsigned_transaction_from_dict(txn_data)
        signature = (self.signature.v, to_int(self.signature.r), to_int(self.signature.s))
        signed_txn = encode_transaction(unsigned_txn, signature)
        impersonated_accounts = self.account_manager.test_accounts._impersonated_accounts

        # If this is a real sender (not impersonated), verify its signature.
        if self.sender and self.sender not in impersonated_accounts:
            recovered_signer = EthAccount.recover_transaction(signed_txn)
            if recovered_signer != self.sender:
                raise SignatureError(
                    f"Recovered signer '{recovered_signer}' doesn't match sender {self.sender}!"
                )

        return signed_txn

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
    access_list: list[AccessList] = Field(default_factory=list, alias="accessList")

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
    access_list: list[AccessList] = Field(default_factory=list, alias="accessList")

    @field_validator("type")
    @classmethod
    def check_type(cls, value):
        return value.value if isinstance(value, TransactionType) else value


class SharedBlobTransaction(DynamicFeeTransaction):
    """
    `EIP-4844 <https://eips.ethereum.org/EIPS/eip-4844>`__ transactions.
    """

    max_fee_per_blob_gas: HexInt = Field(default=0, alias="maxFeePerBlobGas")
    blob_versioned_hashes: list[HexBytes] = Field(default_factory=list, alias="blobVersionedHashes")

    receiver: AddressType = Field(default=ZERO_ADDRESS, alias="to")
    """
    Overridden because EIP-4844 states it cannot be nil.
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
    def debug_logs_typed(self) -> list[tuple[Any]]:
        """
        Extract messages to console outputted by contracts via print() or console.log() statements
        """
        try:
            trace = self.trace
        # Some providers do not implement this, so skip.
        except NotImplementedError:
            logger.debug("Call tree not available, skipping debug log extraction")
            return []

        # If the trace is not available, no logs are available.
        if trace is None or not isinstance(trace, Trace):
            return []

        return list(trace.debug_logs)

    @cached_property
    def contract_type(self) -> Optional[ContractType]:
        if address := (self.receiver or self.contract_address):
            return self.chain_manager.contracts.get(address)

        return None

    @cached_property
    def method_called(self) -> Optional[MethodABI]:
        if not self.contract_type:
            return None

        method_id = self.data[:4]
        if method_id not in self.contract_type.methods:
            return None

        return self.contract_type.methods[method_id]

    @cached_property
    def source_traceback(self) -> SourceTraceback:
        if contract_type := self.contract_type:
            if contract_src := self.local_project._create_contract_source(contract_type):
                try:
                    return SourceTraceback.create(contract_src, self.trace, HexBytes(self.data))
                except Exception as err:
                    # Failing to get a traceback should not halt an Ape application.
                    # Sometimes, a node crashes and we are left with nothing.
                    logger.error(f"Problem retrieving traceback: {err}")
                    pass

        return SourceTraceback.model_validate([])

    def raise_for_status(self):
        err: Optional[TransactionError] = None
        if self.gas_limit is not None and self.ran_out_of_gas:
            err = OutOfGasError(txn=self)

        elif self.status != TransactionStatusEnum.NO_ERROR:
            txn_hash = self.txn_hash
            err = TransactionError(f"Transaction '{txn_hash}' failed.", txn=self)

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
            Union[list[Union[EventABI, "ContractEvent"]], Union[EventABI, "ContractEvent"]]
        ] = None,
    ) -> ContractLogContainer:
        if not self.logs:
            # Short circuit.
            return ContractLogContainer([])

        elif abi is not None:
            if not isinstance(abi, (list, tuple)):
                abi = [abi]

            event_abis: list[EventABI] = [a.abi if not isinstance(a, EventABI) else a for a in abi]
            return ContractLogContainer(
                self.provider.network.ecosystem.decode_logs(self.logs, *event_abis)
            )

        else:
            # If ABI is not provided, decode all events
            addresses = {x["address"] for x in self.logs}
            contract_types = self.chain_manager.contracts.get_multiple(addresses)
            # address → selector → abi
            selectors = {
                address: {encode_hex(keccak(text=abi.selector)): abi for abi in contract.events}
                for address, contract in contract_types.items()
            }

            def get_default_log(
                _log: dict, logs: ContractLogContainer, evt_name: Optional[str] = None
            ) -> ContractLog:
                log_index = _log.get("logIndex", logs[-1].log_index + 1 if logs else 0)

                # NOTE: Happens when decoding fails.
                evt_name = evt_name or f"UnknownLog_WithIndex_{log_index}"

                return ContractLog(
                    block_hash=self.block.hash,
                    block_number=self.block_number,
                    event_arguments={"root": _log["data"]},
                    event_name=f"<{evt_name}>",
                    log_index=log_index,
                    transaction_hash=self.txn_hash,
                    transaction_index=logs[-1].transaction_index if logs else None,
                )

            decoded_logs: ContractLogContainer = ContractLogContainer()
            for log in self.logs:
                if contract_address := log.get("address"):
                    if contract_address in selectors and (topics := log.get("topics")):
                        selector = encode_hex(topics[0])
                        if selector in selectors[contract_address]:
                            event_abi = selectors[contract_address][selector]
                            decoded_logs.extend(
                                self.provider.network.ecosystem.decode_logs([log], event_abi)
                            )

                        elif library_log := self._decode_ds_note(log):
                            decoded_logs.append(library_log)

                        else:
                            # Search for selector in other spots:
                            name = f"UnknownLogWithSelector_{selector}"
                            obj = get_default_log(log, decoded_logs, evt_name=name)
                            decoded_logs.append(obj)

                    elif library_log := self._decode_ds_note(log):
                        decoded_logs.append(library_log)

                    else:
                        name = f"UnknownLogAtAddress_{contract_address}"
                        index = log.get("logIndex")
                        if index is not None:
                            name = f"{name}_AndLogIndex_{index}"

                        obj = get_default_log(log, decoded_logs, evt_name=name)
                        decoded_logs.append(obj)

                elif library_log := self._decode_ds_note(log):
                    decoded_logs.append(library_log)

                else:
                    obj = get_default_log(log, decoded_logs)
                    decoded_logs.append(obj)

            return decoded_logs

    def _decode_ds_note(self, log: dict) -> Optional[ContractLog]:
        # The first topic encodes the function selector
        selector, tail = log["topics"][0][:4], log["topics"][0][4:]
        if sum(tail):
            # non-zero bytes found after selector
            return None

        if not (contract_type := self.chain_manager.contracts.get(log["address"])):
            # contract type for {log['address']} not found
            return None

        try:
            method_abi = contract_type.mutable_methods[selector]
        except KeyError:
            #  selector {to_hex(selector)} not found in {log['address']}
            return None

        # ds-note data field uses either (uint256,bytes) or (bytes) encoding
        # instead of guessing, assume the payload begins right after the selector
        data = decode_hex(log["data"]) if isinstance(log["data"], str) else log["data"]
        input_types = [i.canonical_type for i in method_abi.inputs]
        start_index = data.index(selector) + 4
        values = decode(input_types, data[start_index:])
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
