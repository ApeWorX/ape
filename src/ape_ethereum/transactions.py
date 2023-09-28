import sys
from enum import Enum, IntEnum
from typing import IO, Dict, List, Optional, Union

from eth_abi import decode
from eth_account import Account as EthAccount
from eth_account._utils.legacy_transactions import (
    encode_transaction,
    serializable_unsigned_transaction_from_dict,
)
from eth_utils import decode_hex, encode_hex, keccak, to_hex, to_int
from ethpm_types import ContractType, HexBytes
from ethpm_types.abi import EventABI, MethodABI

from ape._pydantic_compat import BaseModel, Field, root_validator, validator
from ape.api import ReceiptAPI, TransactionAPI
from ape.contracts import ContractEvent
from ape.exceptions import OutOfGasError, SignatureError, TransactionError
from ape.types import CallTreeNode, ContractLog, ContractLogContainer, SourceTraceback
from ape.utils import cached_property


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

        # If this is a real sender (not impersonated), verify its signature.
        if (
            self.sender
            and self.sender not in self.account_manager.test_accounts._impersonated_accounts
            and EthAccount.recover_transaction(signed_txn) != self.sender
        ):
            raise SignatureError("Recovered signer doesn't match sender!")

        return signed_txn

    @property
    def txn_hash(self) -> HexBytes:
        txn_bytes = self.serialize_transaction()
        return HexBytes(keccak(txn_bytes))


class StaticFeeTransaction(BaseTransaction):
    """
    Transactions that are pre-EIP-1559 and use the ``gasPrice`` field.
    """

    gas_price: Optional[int] = Field(None, alias="gasPrice")
    max_priority_fee: Optional[int] = Field(None, exclude=True)
    type: int = Field(TransactionType.STATIC.value, exclude=True)
    max_fee: Optional[int] = Field(None, exclude=True)

    @root_validator(pre=True, allow_reuse=True)
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
    type: int = Field(TransactionType.DYNAMIC.value)
    access_list: List[AccessList] = Field(default_factory=list, alias="accessList")

    @validator("type", allow_reuse=True)
    def check_type(cls, value):
        return value.value if isinstance(value, TransactionType) else value


class AccessListTransaction(BaseTransaction):
    """
    EIP-2930 transactions are similar to legacy transaction with an added access list functionality.
    """

    gas_price: Optional[int] = Field(None, alias="gasPrice")
    type: int = Field(TransactionType.ACCESS_LIST.value)
    access_list: List[AccessList] = Field(default_factory=list, alias="accessList")

    @validator("type", allow_reuse=True)
    def check_type(cls, value):
        return value.value if isinstance(value, TransactionType) else value


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

    @cached_property
    def call_tree(self) -> Optional[CallTreeNode]:
        return self.provider.get_call_tree(self.txn_hash)

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
            return SourceTraceback.create(contract_type, self.trace, HexBytes(self.data))

        return SourceTraceback.parse_obj([])

    def raise_for_status(self):
        if self.gas_limit is not None and self.ran_out_of_gas:
            raise OutOfGasError(txn=self)

        elif self.status != TransactionStatusEnum.NO_ERROR:
            txn_hash = HexBytes(self.txn_hash).hex()
            raise TransactionError(f"Transaction '{txn_hash}' failed.", txn=self)

    def show_trace(self, verbose: bool = False, file: IO[str] = sys.stdout):
        if not (call_tree := self.call_tree):
            return

        call_tree.enrich(use_symbol_for_tokens=True)
        revert_message = None

        if call_tree.failed:
            default_message = "reverted without message"
            returndata = HexBytes(call_tree.raw["returndata"])
            if not to_hex(returndata).startswith(
                "0x08c379a00000000000000000000000000000000000000000000000000000000000000020"
            ):
                revert_message = default_message
            else:
                decoded_result = decode(("string",), returndata[4:])
                if len(decoded_result) == 1:
                    revert_message = f'reverted with message: "{decoded_result[0]}"'
                else:
                    revert_message = default_message

        self.chain_manager._reports.show_trace(
            call_tree,
            sender=self.sender,
            transaction_hash=self.txn_hash,
            revert_message=revert_message,
            verbose=verbose,
            file=file,
        )

    def show_gas_report(self, file: IO[str] = sys.stdout):
        if not (call_tree := self.call_tree):
            return

        call_tree.enrich()

        # Enrich transfers.
        if (
            call_tree.contract_id.startswith("Transferring ")
            and self.receiver is not None
            and self.receiver in self.account_manager
        ):
            receiver_id = self.account_manager[self.receiver].alias or self.receiver
            call_tree.method_id = f"to:{receiver_id}"

        elif call_tree.contract_id.startswith("Transferring "):
            call_tree.method_id = f"to:{self.receiver}"

        self.chain_manager._reports.show_gas(call_tree, file=file)

    def show_source_traceback(self, file: IO[str] = sys.stdout):
        self.chain_manager._reports.show_source_traceback(
            self.source_traceback, file=file, failing=self.failed
        )

    def decode_logs(
        self,
        abi: Optional[
            Union[List[Union[EventABI, "ContractEvent"]], Union[EventABI, "ContractEvent"]]
        ] = None,
    ) -> ContractLogContainer:
        if abi is not None:
            if not isinstance(abi, (list, tuple)):
                abi = [abi]

            event_abis: List[EventABI] = [a.abi if not isinstance(a, EventABI) else a for a in abi]
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
                _log: Dict, logs: ContractLogContainer, name: Optional[str] = None
            ) -> ContractLog:
                # For when we fail to decode.
                if not name:
                    name = "UnknownLog"
                    index = _log.get("logIndex")
                    if index is not None:
                        name = f"{name}_WithIndex_{index}"

                return ContractLog(
                    block_hash=self.block.hash,
                    block_number=self.block_number,
                    event_arguments={"__root__": _log["data"]},
                    event_name=f"<{name}>",
                    log_index=logs[-1].log_index + 1 if logs else 0,
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
                            obj = get_default_log(log, decoded_logs, name=name)
                            decoded_logs.append(obj)

                    elif library_log := self._decode_ds_note(log):
                        decoded_logs.append(library_log)

                    else:
                        name = f"UnknownLogAtAddress_{contract_address}"
                        index = log.get("logIndex")
                        if index is not None:
                            name = f"{name}_AndLogIndex_{index}"

                        obj = get_default_log(log, decoded_logs, name=name)
                        decoded_logs.append(obj)

                elif library_log := self._decode_ds_note(log):
                    decoded_logs.append(library_log)

                else:
                    obj = get_default_log(log, decoded_logs)
                    decoded_logs.append(obj)

            return decoded_logs

    def _decode_ds_note(self, log: Dict) -> Optional[ContractLog]:
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
            #  selector {selector.hex()} not found in {log['address']}
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
