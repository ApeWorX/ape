from typing import Any, Dict, List, Optional, Tuple

from eth_abi import decode_abi as abi_decode
from eth_abi import encode_abi as abi_encode
from eth_abi.exceptions import InsufficientDataBytes
from eth_account import Account as EthAccount  # type: ignore
from eth_account._utils.legacy_transactions import (
    encode_transaction,
    serializable_unsigned_transaction_from_dict,
)
from eth_typing import HexStr
from eth_utils import add_0x_prefix, keccak, to_bytes, to_checksum_address, to_int
from ethpm_types import ABI
from hexbytes import HexBytes

from ape.api import (
    BlockAPI,
    BlockConsensusAPI,
    BlockGasAPI,
    ConfigItem,
    EcosystemAPI,
    ReceiptAPI,
    TransactionAPI,
    TransactionStatusEnum,
    TransactionType,
)
from ape.contracts import ContractLog
from ape.exceptions import DecodingError, OutOfGasError, SignatureError, TransactionError
from ape.types import AddressType

NETWORKS = {
    # chain_id, network_id
    "mainnet": (1, 1),
    "ropsten": (3, 3),
    "kovan": (42, 42),
    "rinkeby": (4, 4),
    "goerli": (5, 5),
}


class NetworkConfig(ConfigItem):
    required_confirmations: int = 0
    default_provider: str = "geth"
    block_time: int = 0


class EthereumConfig(ConfigItem):
    mainnet: NetworkConfig = NetworkConfig(required_confirmations=7, block_time=13)  # type: ignore
    ropsten: NetworkConfig = NetworkConfig(required_confirmations=12, block_time=15)  # type: ignore
    kovan: NetworkConfig = NetworkConfig(required_confirmations=2, block_time=4)  # type: ignore
    rinkeby: NetworkConfig = NetworkConfig(required_confirmations=2, block_time=15)  # type: ignore
    goerli: NetworkConfig = NetworkConfig(required_confirmations=2, block_time=15)  # type: ignore
    development: NetworkConfig = NetworkConfig(default_provider="test")  # type: ignore


class BaseTransaction(TransactionAPI):
    def as_dict(self) -> dict:
        data = super().as_dict()

        # Clean up data to what we expect
        data["chainId"] = data.pop("chain_id")

        receiver = data.pop("receiver")
        if receiver:
            data["to"] = receiver

        # NOTE: sender is needed sometimes for estimating gas
        # but is it no needed during publish (and may error if included).
        sender = data.pop("sender")
        if sender:
            data["from"] = sender

        data["gas"] = data.pop("gas_limit")

        if "required_confirmations" in data:
            data.pop("required_confirmations")

        # NOTE: Don't include signature
        data.pop("signature")

        return {key: value for key, value in data.items() if value is not None}

    def encode(self) -> bytes:
        if not self.signature:
            raise SignatureError("The transaction is not signed.")

        txn_data = self.as_dict()

        # Don't publish from
        if "from" in txn_data:
            del txn_data["from"]

        unsigned_txn = serializable_unsigned_transaction_from_dict(txn_data)
        signature = (self.signature.v, to_int(self.signature.r), to_int(self.signature.s))

        signed_txn = encode_transaction(unsigned_txn, signature)

        if self.sender and EthAccount.recover_transaction(signed_txn) != self.sender:
            raise SignatureError("Recovered Signer doesn't match sender!")

        return signed_txn


class StaticFeeTransaction(BaseTransaction):
    """
    Transactions that are pre-EIP-1559 and use the ``gasPrice`` field.
    """

    gas_price: int = None  # type: ignore
    type: TransactionType = TransactionType.STATIC

    @property
    def max_fee(self) -> int:
        return (self.gas_limit or 0) * (self.gas_price or 0)

    @max_fee.setter
    def max_fee(self, valie):
        raise NotImplementedError("Max fee is not settable for static-fee transactions.")

    def as_dict(self):
        data = super().as_dict()
        if "gas_price" in data:
            data["gasPrice"] = data.pop("gas_price")

        data.pop("type")

        return data


class DynamicFeeTransaction(BaseTransaction):
    """
    Transactions that are post-EIP-1559 and use the ``maxFeePerGas``
    and ``maxPriorityFeePerGas`` fields.
    """

    max_fee: int = None  # type: ignore
    max_priority_fee: int = None  # type: ignore
    type: TransactionType = TransactionType.DYNAMIC

    def as_dict(self):
        data = super().as_dict()
        if "max_fee" in data:
            data["maxFeePerGas"] = data.pop("max_fee")
        if "max_priority_fee" in data:
            data["maxPriorityFeePerGas"] = data.pop("max_priority_fee")

        if isinstance(data["type"], TransactionType):
            data["type"] = data.pop("type").value

        return data


class Receipt(ReceiptAPI):
    def raise_for_status(self):
        """
        Raise an error for the given transaction, if the transaction has failed.

        Raises:
            :class:`~ape.exceptions.OutOfGasError`: When the transaction failed
              and ran out of gas.
            :class:`~ape.exceptions.TransactionError`: When the transaction has a
              failing status otherwise.
        """

        if self.gas_limit and self.ran_out_of_gas:
            raise OutOfGasError()
        elif self.status != TransactionStatusEnum.NO_ERROR:
            txn_hash = HexBytes(self.txn_hash).hex()
            raise TransactionError(message=f"Transaction '{txn_hash}' failed.")

    @classmethod
    def decode(cls, data: dict) -> ReceiptAPI:
        status = data.get("status")
        if status:
            if isinstance(status, str) and status.isnumeric():
                status = int(status)

            status = TransactionStatusEnum(status)

        txn_hash = data["hash"].hex() if isinstance(data["hash"], HexBytes) else data["hash"]
        return cls(  # type: ignore
            provider=data.get("provider"),
            required_confirmations=data.get("required_confirmations", 0),
            txn_hash=txn_hash,
            status=status,
            block_number=data["blockNumber"],
            gas_used=data["gasUsed"],
            gas_price=data["gasPrice"],
            gas_limit=data.get("gas") or data.get("gasLimit"),
            logs=data.get("logs"),
            contract_address=data.get("contractAddress"),
            sender=data["from"],
            receiver=data["to"],
            nonce=data.get("nonce"),
        )


class BlockGasFee(BlockGasAPI):
    @classmethod
    def decode(cls, data: Dict) -> BlockGasAPI:
        return BlockGasFee(  # type: ignore
            gas_limit=data["gasLimit"],
            gas_used=data["gasUsed"],
            base_fee=data.get("baseFeePerGas"),
        )


class BlockConsensus(BlockConsensusAPI):
    difficulty: Optional[int] = None
    total_difficulty: Optional[int] = None

    @classmethod
    def decode(cls, data: Dict) -> BlockConsensusAPI:
        return cls(
            difficulty=data.get("difficulty"), total_difficulty=data.get("totalDifficulty")
        )  # type: ignore


class Block(BlockAPI):
    @classmethod
    def decode(cls, data: Dict) -> BlockAPI:
        return cls(  # type: ignore
            gas_data=BlockGasFee.decode(data),
            consensus_data=BlockConsensus.decode(data),
            number=data["number"],
            size=data.get("size"),
            timestamp=data.get("timestamp"),
            hash=data.get("hash"),
            parent_hash=data.get("hash"),
        )


class Ethereum(EcosystemAPI):
    transaction_types = {
        TransactionType.STATIC: StaticFeeTransaction,
        TransactionType.DYNAMIC: DynamicFeeTransaction,
    }
    receipt_class = Receipt
    block_class = Block

    @property
    def config(self) -> EthereumConfig:
        return self.config_manager.get_config("ethereum")  # type: ignore

    def encode_calldata(self, abi: ABI, *args) -> bytes:
        if abi.inputs:
            input_types = [i.canonical_type for i in abi.inputs]
            return abi_encode(input_types, args)

        else:
            return HexBytes(b"")

    def decode_calldata(self, abi: ABI, raw_data: bytes) -> Tuple[Any, ...]:
        output_types = [o.canonical_type for o in abi.outputs]  # type: ignore
        try:
            vm_return_values = abi_decode(output_types, raw_data)
            if not vm_return_values:
                return vm_return_values

            if not isinstance(vm_return_values, (tuple, list)):
                vm_return_values = (vm_return_values,)

            output_values: List[Any] = []
            for index in range(len(vm_return_values)):
                value = vm_return_values[index]
                if index < len(output_types) and output_types[index] == "address":
                    value = to_checksum_address(value)

                output_values.append(value)

            return tuple(output_values)

        except InsufficientDataBytes as err:
            raise DecodingError() from err

    def encode_deployment(
        self, deployment_bytecode: bytes, abi: Optional[ABI], *args, **kwargs
    ) -> BaseTransaction:
        txn = self.create_transaction(**kwargs)
        txn.data = deployment_bytecode

        # Encode args, if there are any
        if abi:
            txn.data += self.encode_calldata(abi, *args)

        return txn  # type: ignore

    def encode_transaction(
        self,
        address: AddressType,
        abi: ABI,
        *args,
        **kwargs,
    ) -> BaseTransaction:
        txn = self.create_transaction(receiver=address, **kwargs)

        # Add method ID
        txn.data = keccak(to_bytes(text=abi.selector))[:4]
        txn.data += self.encode_calldata(abi, *args)

        return txn  # type: ignore

    def create_transaction(self, **kwargs) -> TransactionAPI:
        """
        Returns a transaction using the given constructor kwargs.

        Returns:
            :class:`~ape.api.providers.TransactionAPI`
        """
        if "type" in kwargs:
            type_kwarg = kwargs["type"]
            if type_kwarg is None:
                type_kwarg = TransactionType.DYNAMIC.value
            elif isinstance(type_kwarg, int):
                type_kwarg = f"0{type_kwarg}"
            elif isinstance(type_kwarg, bytes):
                type_kwarg = type_kwarg.hex()

            suffix = type_kwarg.replace("0x", "")
            if len(suffix) == 1:
                type_kwarg = f"{type_kwarg.rstrip(suffix)}0{suffix}"

            version_str = add_0x_prefix(HexStr(type_kwarg))
            version = TransactionType(version_str)
        elif "gas_price" in kwargs:
            version = TransactionType.STATIC
        else:
            version = TransactionType.DYNAMIC

        txn_class = self.transaction_types[version]
        kwargs["type"] = version.value

        if "required_confirmations" not in kwargs or kwargs["required_confirmations"] is None:
            # Attempt to use default required-confirmations from `ape-config.yaml`.
            required_confirmations = 0
            active_provider = self.network_manager.active_provider
            if active_provider:
                required_confirmations = active_provider.network.required_confirmations

            kwargs["required_confirmations"] = required_confirmations

        return txn_class(**kwargs)  # type: ignore

    def decode_event(self, abi: ABI, receipt: "ReceiptAPI") -> "ContractLog":
        filter_id = keccak(to_bytes(text=abi.selector))
        event_data = next(log for log in receipt.logs if log["filter_id"] == filter_id)

        return ContractLog(  # type: ignore
            name=abi.name,
            inputs={i.name: event_data[i.name] for i in abi.inputs},  # type: ignore
        )
