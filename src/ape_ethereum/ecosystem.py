from typing import Any, Optional

from eth_abi import decode_abi as abi_decode
from eth_abi import encode_abi as abi_encode
from eth_abi.exceptions import InsufficientDataBytes
from eth_account import Account as EthAccount  # type: ignore
from eth_account._utils.legacy_transactions import (  # type: ignore
    encode_transaction,
    serializable_unsigned_transaction_from_dict,
)
from eth_utils import keccak, to_bytes  # type: ignore
from hexbytes import HexBytes

from ape.api import ContractLog, EcosystemAPI, ReceiptAPI, TransactionAPI, TransactionStatusEnum
from ape.types import ABI, AddressType

NETWORKS = {
    # chain_id, network_id
    "mainnet": (1, 1),
    "ropsten": (3, 3),
    "kovan": (42, 42),
    "rinkeby": (4, 4),
    "goerli": (420, 420),
}


# TODO: Fix this to add support for TypedTransaction
class Transaction(TransactionAPI):
    def is_valid(self) -> bool:
        return False

    def as_dict(self) -> dict:
        data = super().as_dict()

        # Clean up data to what we expect
        data["chainId"] = data.pop("chain_id")

        receiver = data.pop("receiver")
        if receiver:
            data["to"] = receiver

        data["gas"] = data.pop("gas_limit")
        data["gasPrice"] = data.pop("gas_price")

        # NOTE: Don't publish signature or sender
        data.pop("signature")
        data.pop("sender")

        return data

    def encode(self) -> bytes:
        if not self.signature:
            raise Exception("Transaction is not signed!")

        txn_data = self.as_dict()
        unsigned_txn = serializable_unsigned_transaction_from_dict(txn_data)
        signature = (self.signature.v, self.signature.r, self.signature.s)

        signed_txn = encode_transaction(unsigned_txn, signature)

        if self.sender and EthAccount.recover_transaction(signed_txn) != self.sender:
            raise Exception("Recovered Signer doesn't match sender!")

        return signed_txn


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

    def encode_transaction(
        self,
        address: AddressType,
        abi: ABI,
        *args,
        **kwargs,
    ) -> Transaction:
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
