from eth_account._utils.transactions import (  # type: ignore
    encode_transaction,
    serializable_unsigned_transaction_from_dict,
)
from eth_utils import to_int
from rlp import decode as rlp_decode  # type: ignore
from rlp import encode as rlp_encode  # type: ignore

from ape.api import (
    ContractCallAPI,
    ContractConstructorAPI,
    ContractEventAPI,
    ContractTransactionAPI,
    EcosystemAPI,
    ReceiptAPI,
    TransactionAPI,
    TransactionStatusEnum,
)

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
        del data["chain_id"]
        del data["sender"]
        data["to"] = data["receiver"]
        del data["receiver"]
        data["gas"] = data["gas_limit"]
        del data["gas_limit"]
        data["gasPrice"] = data["gas_price"]
        del data["gas_price"]

        # NOTE: Don't publish signature
        del data["signature"]

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


class ContractConstructor(ContractConstructorAPI):
    def __call__(self, *args, **kwargs) -> TransactionAPI:
        txn = Transaction(**kwargs)  # type: ignore
        txn.data = self.deployment_bytecode + rlp_encode(self.inputs, *args)
        return txn


class ContractCall(ContractCallAPI):
    def __call__(self, *args, **kwargs) -> TransactionAPI:
        txn = Transaction(**kwargs)  # type: ignore
        txn.data = rlp_encode(self.inputs, *args)
        return txn


class ContractTransaction(ContractTransactionAPI):
    def __call__(self, *args, **kwargs) -> TransactionAPI:
        txn = Transaction(**kwargs)  # type: ignore
        txn.data = rlp_encode(self.inputs, *args)
        return txn


class ContractEvent(ContractEventAPI):
    def decode(self, data: bytes) -> dict:
        event_data = rlp_decode(self.inputs, data)
        return event_data


class Ethereum(EcosystemAPI):
    transaction_class = Transaction
    receipt_class = Receipt

    contract_constructor_class = ContractConstructor
    contract_call_class = ContractCall
    contract_transaction_class = ContractTransaction
    contract_event_class = ContractEvent
