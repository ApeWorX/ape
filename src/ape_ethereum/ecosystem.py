from typing import Any, Optional

from eth_abi import decode_abi as abi_decode
from eth_abi import encode_abi as abi_encode
from eth_abi.exceptions import InsufficientDataBytes
from eth_account._utils.transactions import (  # type: ignore
    encode_transaction,
    serializable_unsigned_transaction_from_dict,
)
from eth_utils import keccak, to_bytes, to_int  # type: ignore
from hexbytes import HexBytes

from ape.api import ContractLog, EcosystemAPI, ReceiptAPI, TransactionAPI, TransactionStatusEnum
from ape.types import ABI

NETWORKS = {
    # chain_id, network_id
    "mainnet": (1, 1),
    "ropsten": (3, 3),
    "kovan": (42, 42),
    "rinkeby": (4, 4),
    "goerli": (420, 420),
}


class Transaction(TransactionAPI):
    def is_valid(self) -> bool:
        return False

    def as_dict(self) -> dict:
        data = super().as_dict()

        # Clean up data to what we expect
        data.pop("chain_id")
        data.pop("sender")
        data["to"] = data.pop("receiver")
        data["gas"] = data.pop("gas_limit")
        data["gasPrice"] = data.pop("gas_price")

        # NOTE: Don't publish signature
        data.pop("signature")

        return data

    def encode(self) -> bytes:
        data = self.as_dict()
        unsigned_txn = serializable_unsigned_transaction_from_dict(data)
        return encode_transaction(
            unsigned_txn,
            (
                to_int(self.signature[:1]),
                to_int(self.signature[1:33]),
                to_int(self.signature[33:65]),
            ),
        )


class Receipt(ReceiptAPI):
    @classmethod
    def decode(cls, data: dict) -> ReceiptAPI:
        return cls(  # type: ignore
            txn_hash=data["hash"],
            status=TransactionStatusEnum(data["status"]),
            block_number=data["blockNumber"],
            gas_used=data["gasUsed"],
            gas_price=data["gasPrice"],
            logs=data["logs"],
            contract_address=data["contractAddress"],
        )


class Ethereum(EcosystemAPI):
    transaction_class = Transaction
    receipt_class = Receipt

    def encode_calldata(self, abi: ABI, *args) -> bytes:
        if abi.inputs:
            input_types = [i.canonical_type for i in abi.inputs]
            return abi_encode(input_types, args)

        else:
            return HexBytes(b"")

    def decode_calldata(self, abi: ABI, raw_data: bytes) -> Any:
        output_types = [o.canonical_type for o in abi.outputs]
        try:
            return abi_decode(output_types, raw_data)

        except InsufficientDataBytes as e:
            raise Exception("Output corrupted") from e

    def encode_deployment(
        self, deployment_bytecode: bytes, abi: Optional[ABI], *args, **kwargs
    ) -> Transaction:
        txn = Transaction(**kwargs)  # type: ignore
        txn.data = deployment_bytecode

        # Encode args, if there are any
        if abi:
            txn.data += self.encode_calldata(abi, *args)

        return txn

    def encode_transaction(self, address: str, abi: ABI, *args, **kwargs) -> Transaction:
        txn = Transaction(receiver=address, **kwargs)  # type: ignore

        # Add method ID
        txn.data = keccak(to_bytes(text=abi.selector))[:4]
        txn.data += self.encode_calldata(abi, *args)

        return txn

    def decode_event(self, abi: ABI, receipt: "ReceiptAPI") -> "ContractLog":
        filter_id = keccak(to_bytes(text=abi.selector))
        event_data = next(log for log in receipt.logs if log["filter_id"] == filter_id)
        return ContractLog(  # type: ignore
            name=abi.name,
            inputs={i.name: event_data[i.name] for i in abi.inputs},
        )
