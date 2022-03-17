import itertools
from typing import Any, Dict, Iterator, List, Optional, Tuple, Union

from eth_abi import decode_abi as abi_decode
from eth_abi import encode_abi as abi_encode
from eth_abi import grammar
from eth_abi.abi import decode_abi, decode_single, encode_single
from eth_abi.exceptions import InsufficientDataBytes
from eth_account import Account as EthAccount  # type: ignore
from eth_account._utils.legacy_transactions import (
    encode_transaction,
    serializable_unsigned_transaction_from_dict,
)
from eth_typing import HexStr
from eth_utils import add_0x_prefix, hexstr_if_str, keccak, to_bytes, to_checksum_address, to_int
from eth_utils.abi import collapse_if_tuple
from ethpm_types.abi import ConstructorABI, EventABI, EventABIType, MethodABI
from hexbytes import HexBytes
from pydantic import Field, root_validator, validator

from ape.api import (
    AccountAPI,
    BlockAPI,
    BlockConsensusAPI,
    BlockGasAPI,
    EcosystemAPI,
    PluginConfig,
    ReceiptAPI,
    TransactionAPI,
    TransactionStatusEnum,
    TransactionType,
)
from ape.api.networks import LOCAL_NETWORK_NAME
from ape.exceptions import DecodingError, OutOfGasError, SignatureError, TransactionError
from ape.types import AddressType, ContractLog

NETWORKS = {
    # chain_id, network_id
    "mainnet": (1, 1),
    "ropsten": (3, 3),
    "kovan": (42, 42),
    "rinkeby": (4, 4),
    "goerli": (5, 5),
}


class NetworkConfig(PluginConfig):
    required_confirmations: int = 0
    default_provider: str = "geth"
    block_time: int = 0


class EthereumConfig(PluginConfig):
    mainnet: NetworkConfig = NetworkConfig(required_confirmations=7, block_time=13)  # type: ignore
    mainnet_fork: NetworkConfig = NetworkConfig(default_provider="test")  # type: ignore
    ropsten: NetworkConfig = NetworkConfig(required_confirmations=12, block_time=15)  # type: ignore
    kovan: NetworkConfig = NetworkConfig(required_confirmations=2, block_time=4)  # type: ignore
    rinkeby: NetworkConfig = NetworkConfig(required_confirmations=2, block_time=15)  # type: ignore
    goerli: NetworkConfig = NetworkConfig(required_confirmations=2, block_time=15)  # type: ignore
    local: NetworkConfig = NetworkConfig(default_provider="test")  # type: ignore
    default_network: str = LOCAL_NETWORK_NAME


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
    type: TransactionType = Field(TransactionType.STATIC, exclude=True)
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
    type: TransactionType = Field(TransactionType.DYNAMIC)

    @validator("type")
    def check_type(cls, value):

        if isinstance(value, TransactionType):
            return value.value

        return value


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


class BlockGasFee(BlockGasAPI):
    @classmethod
    def decode(cls, data: Dict) -> BlockGasAPI:
        return BlockGasFee(**data)  # type: ignore


class BlockConsensus(BlockConsensusAPI):
    @classmethod
    def decode(cls, data: Dict) -> BlockConsensusAPI:
        return cls(**data)  # type: ignore


class Block(BlockAPI):
    """
    Class for representing a block on a chain.
    """


class Ethereum(EcosystemAPI):
    @property
    def config(self) -> EthereumConfig:
        return self.config_manager.get_config("ethereum")  # type: ignore

    def serialize_transaction(self, transaction: TransactionAPI) -> bytes:
        if not transaction.signature:
            raise SignatureError("The transaction is not signed.")

        txn_data = transaction.dict()

        unsigned_txn = serializable_unsigned_transaction_from_dict(txn_data)
        signature = (
            transaction.signature.v,
            to_int(transaction.signature.r),
            to_int(transaction.signature.s),
        )

        signed_txn = encode_transaction(unsigned_txn, signature)

        if transaction.sender and EthAccount.recover_transaction(signed_txn) != transaction.sender:
            raise SignatureError("Recovered Signer doesn't match sender!")

        return signed_txn

    def decode_receipt(self, data: dict) -> ReceiptAPI:
        status = data.get("status")
        if status:
            if isinstance(status, str) and status.isnumeric():
                status = int(status)

            status = TransactionStatusEnum(status)

        txn_hash = data.get("hash")

        if txn_hash:
            txn_hash = data["hash"].hex() if isinstance(data["hash"], HexBytes) else data["hash"]

        return Receipt(  # type: ignore
            provider=data.get("provider"),
            required_confirmations=data.get("required_confirmations", 0),
            txn_hash=txn_hash,
            status=status,
            block_number=data["blockNumber"],
            gas_used=data["gasUsed"],
            gas_price=data["gasPrice"],
            gas_limit=data.get("gas") or data.get("gasLimit"),
            logs=data.get("logs", []),
            contract_address=data.get("contractAddress"),
            sender=data["from"],
            receiver=data["to"] or "",
            nonce=data["nonce"] if "nonce" in data and data["nonce"] != "" else None,
        )

    def decode_block(self, data: Dict) -> BlockAPI:

        return Block(  # type: ignore
            gas_data=BlockGasFee.decode(data),
            consensus_data=BlockConsensus.decode(data),
            number=data.get("number"),
            size=data.get("size"),
            timestamp=data.get("timestamp"),
            hash=data.get("hash"),
            parent_hash=data.get("hash"),
        )

    def encode_calldata(self, abi: Union[ConstructorABI, MethodABI], *args) -> bytes:
        if abi.inputs:
            input_types = [i.canonical_type for i in abi.inputs]
            return abi_encode(input_types, args)

        else:
            return HexBytes(b"")

    def decode_calldata(self, abi: MethodABI, raw_data: bytes) -> Tuple[Any, ...]:
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
        self, deployment_bytecode: HexBytes, abi: ConstructorABI, *args, **kwargs
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
        abi: MethodABI,
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

        transaction_types = {
            TransactionType.STATIC: StaticFeeTransaction,
            TransactionType.DYNAMIC: DynamicFeeTransaction,
        }

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

        txn_class = transaction_types[version]
        kwargs["type"] = version.value

        if "required_confirmations" not in kwargs or kwargs["required_confirmations"] is None:
            # Attempt to use default required-confirmations from `ape-config.yaml`.
            required_confirmations = 0
            active_provider = self.network_manager.active_provider
            if active_provider:
                required_confirmations = active_provider.network.required_confirmations

            kwargs["required_confirmations"] = required_confirmations

        return txn_class(**kwargs)  # type: ignore

    def encode_log_filter(self, abi: EventABI, **filter_args) -> Dict:
        filter_data = {}

        if "address" in filter_args:
            address = filter_args.pop("address")
            if not isinstance(address, (list, tuple)):
                address = [address]

            addresses = [self.conversion_manager.convert(a, AddressType) for a in address]
            filter_data["address"] = addresses

        if "fromBlock" in filter_args:
            filter_data["fromBlock"] = filter_args.pop("fromBlock")

        if "toBlock" in filter_args:
            filter_data["toBlock"] = filter_args.pop("toBlock")

        if "topics" not in filter_args:
            event_signature_hash = keccak(text=abi.selector).hex()
            filter_data["topics"] = [event_signature_hash]

            search_topics = [
                self.conversion_manager.convert(a, AddressType) if isinstance(a, AccountAPI) else a
                for a in filter_args.values()
            ]

            # Add remaining kwargs as topics to filter on.
            topics = LogInputs(abi, True)
            encoded_topic_data = [
                encode_single(topic_type, topic_data).hex()  # type: ignore
                for topic_type, topic_data in zip(topics.types, search_topics)
            ]
            filter_data["topics"].extend(encoded_topic_data)
        else:
            filter_data["topics"] = filter_args.pop("topics")

        return filter_data

    def decode_logs(self, abi: EventABI, data: List[Dict]) -> Iterator["ContractLog"]:
        event_id_bytes = keccak(to_bytes(text=abi.selector))
        matching_logs = [log for log in data if log["topics"][0] == event_id_bytes]
        if not matching_logs:
            raise DecodingError(f"No logs found with ID '{abi.selector}'.")

        # Process indexed data (topics)
        abi_topics = LogInputs(abi, indexed=True)
        abi_data = LogInputs(abi, indexed=False)

        # Verify no duplicate names
        duplicate_names = set(abi_topics.names).intersection(abi_data.names)
        if duplicate_names:
            duplicate_names_str = ", ".join([n for n in duplicate_names if n])
            raise DecodingError(
                "The following argument names are duplicated "
                f"between event inputs: '{duplicate_names_str}'."
            )

        for log in matching_logs:
            indexed_data = log["topics"] if log.get("anonymous", False) else log["topics"][1:]
            log_data = hexstr_if_str(to_bytes, log["data"])  # type: ignore

            if len(indexed_data) != len(abi_topics.types):
                raise DecodingError(
                    f"Expected '{len(indexed_data)}' log topics.  Got '{len(abi_topics.types)}'."
                )

            decoded_topic_data = [
                decode_single(topic_type, topic_data)  # type: ignore
                for topic_type, topic_data in zip(abi_topics.types, indexed_data)
            ]
            decoded_log_data = decode_abi(abi_data.types, log_data)  # type: ignore
            event_args = dict(
                itertools.chain(
                    zip(abi_topics.names, decoded_topic_data),
                    zip(abi_data.names, decoded_log_data),
                )
            )
            yield ContractLog(name=abi.name, data=event_args)  # type: ignore


def _get_event_abi_types(abi_inputs: List[Dict]) -> Iterator[Union[str, Dict]]:
    for abi_input in abi_inputs:
        abi_type = grammar.parse(abi_input["type"])
        if abi_type.is_dynamic:
            yield "bytes32"
        else:
            yield collapse_if_tuple(abi_input)


class LogInputs:
    def __init__(self, abi: EventABI, indexed: bool):
        self.abi = abi
        self._indexed = indexed

    @property
    def values(self) -> List[EventABIType]:
        return [i for i in self.abi.inputs if i.indexed == self._indexed]

    @property
    def names(self) -> List[str]:
        return [abi.name for abi in self.values if abi.name]

    @property
    def normalized_values(self) -> List[Dict]:
        return [abi.dict() for abi in self.values]

    @property
    def types(self) -> List[Union[str, Dict]]:
        return [t for t in _get_event_abi_types(self.normalized_values)]
