import itertools
from typing import Any, Dict, Iterator, List, Optional, Tuple, Union

from eth_abi import decode_abi as abi_decode
from eth_abi import encode_abi as abi_encode
from eth_abi.abi import decode_abi, decode_single
from eth_abi.exceptions import InsufficientDataBytes
from eth_typing import HexStr
from eth_utils import add_0x_prefix, hexstr_if_str, keccak, to_bytes, to_checksum_address
from ethpm_types.abi import ConstructorABI, EventABI, EventABIType, MethodABI
from hexbytes import HexBytes

from ape.api import (
    BlockAPI,
    BlockConsensusAPI,
    BlockGasAPI,
    EcosystemAPI,
    PluginConfig,
    ReceiptAPI,
    TransactionAPI,
)
from ape.api.networks import LOCAL_NETWORK_NAME
from ape.exceptions import DecodingError
from ape.types import AddressType, ContractLog, RawAddress
from ape.utils import LogInputABICollection, Struct, StructParser, is_array, returns_array
from ape_ethereum.transactions import (
    BaseTransaction,
    DynamicFeeTransaction,
    Receipt,
    StaticFeeTransaction,
    TransactionStatusEnum,
    TransactionType,
)

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

    default_provider: Optional[str] = "geth"
    """
    The default provider to use. If set to ``None``, ape will rely on
    an external plugin supplying the provider implementation, such as
    ``ape-hardhat`` supplying forked-network providers.
    """

    block_time: int = 0


class EthereumConfig(PluginConfig):
    mainnet: NetworkConfig = NetworkConfig(required_confirmations=7, block_time=13)  # type: ignore
    mainnet_fork: NetworkConfig = NetworkConfig(default_provider=None)  # type: ignore
    ropsten: NetworkConfig = NetworkConfig(required_confirmations=12, block_time=15)  # type: ignore
    ropsten_fork: NetworkConfig = NetworkConfig(default_provider=None)  # type: ignore
    kovan: NetworkConfig = NetworkConfig(required_confirmations=2, block_time=4)  # type: ignore
    kovan_fork: NetworkConfig = NetworkConfig(default_provider=None)  # type: ignore
    rinkeby: NetworkConfig = NetworkConfig(required_confirmations=2, block_time=15)  # type: ignore
    rinkeby_fork: NetworkConfig = NetworkConfig(default_provider=None)  # type: ignore
    goerli: NetworkConfig = NetworkConfig(required_confirmations=2, block_time=15)  # type: ignore
    goerli_fork: NetworkConfig = NetworkConfig(default_provider=None)  # type: ignore
    local: NetworkConfig = NetworkConfig(default_provider="test")  # type: ignore
    default_network: str = LOCAL_NETWORK_NAME


class BlockGasFee(BlockGasAPI):
    @classmethod
    def decode(cls, data: Dict) -> BlockGasAPI:
        return BlockGasFee.parse_obj(data)


class BlockConsensus(BlockConsensusAPI):
    @classmethod
    def decode(cls, data: Dict) -> BlockConsensusAPI:
        return cls(**data)  # type: ignore


class Block(BlockAPI):
    """
    Class for representing a block on a chain.
    """


def parse_output_type(output_type: str) -> Union[str, Tuple, List]:
    if not output_type.startswith("("):
        return output_type

    # Strip off first opening parens
    output_type = output_type[1:]
    found_types: List[Union[str, Tuple, List]] = []

    while output_type:
        if output_type.startswith(")"):
            result = tuple(found_types)
            if "[" in output_type:
                return [result]

            return result

        elif output_type[0] == "(" and ")" in output_type:
            # A tuple within the tuple
            end_index = output_type.index(")") + 1
            found_type = parse_output_type(output_type[:end_index])
            output_type = output_type[end_index:]

            if output_type.startswith("[") and "]" in output_type:
                end_array_index = output_type.index("]") + 1
                found_type = [found_type]
                output_type = output_type[end_array_index:].lstrip(",")

        else:
            found_type = output_type.split(",")[0].rstrip(")")
            end_index = len(found_type) + 1
            output_type = output_type[end_index:]

        if isinstance(found_type, str) and "[" in found_type and ")" in found_type:
            parts = found_type.split(")")
            found_type = parts[0]
            output_type = f"){parts[1]}"

        if found_type:
            found_types.append(found_type)

    return tuple(found_types)


class Ethereum(EcosystemAPI):
    @property
    def config(self) -> EthereumConfig:
        return self.config_manager.get_config("ethereum")  # type: ignore

    @classmethod
    def decode_address(cls, raw_address: RawAddress) -> AddressType:
        if isinstance(raw_address, int):
            raw_address = HexBytes(raw_address)

        return to_checksum_address(raw_address)

    @classmethod
    def encode_address(cls, address: AddressType) -> RawAddress:
        return str(address)

    def serialize_transaction(self, transaction: TransactionAPI) -> bytes:
        return transaction.serialize_transaction()

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
        # TODO: when we flatten the Block structure, remove these hacks
        if "gas_data" in data:
            data.update(data.pop("gas_data"))
        if "consensus_data" in data:
            data.update(data.pop("consensus_data"))
        return Block(  # type: ignore
            gas_data=BlockGasFee.decode(data),
            consensus_data=BlockConsensus.decode(data),
            number=data.get("number"),
            size=data.get("size"),
            timestamp=data.get("timestamp"),
            hash=data.get("hash"),
            # TODO: when we flatten the Block structure, remove this hack.
            parent_hash=data.get("parentHash") or data.get("parent_hash"),
        )

    def encode_calldata(self, abi: Union[ConstructorABI, MethodABI], *args) -> bytes:
        if abi.inputs:
            input_types = [i.canonical_type for i in abi.inputs]
            return abi_encode(input_types, args)

        else:
            return HexBytes(b"")

    def decode_returndata(self, abi: MethodABI, raw_data: bytes) -> Tuple[Any, ...]:
        output_types = [o.canonical_type for o in abi.outputs]  # type: ignore
        try:
            vm_return_values = abi_decode(output_types, raw_data)
        except InsufficientDataBytes as err:
            raise DecodingError() from err

        if not vm_return_values:
            return vm_return_values

        if not isinstance(vm_return_values, (tuple, list)):
            vm_return_values = (vm_return_values,)

        output_values: List[Any] = []
        for index in range(len(vm_return_values)):
            if index >= len(output_types):
                break

            value = vm_return_values[index]
            output_type = parse_output_type(output_types[index])
            output_values.append(self._decode_primitive_value(value, output_type))

        parser = StructParser(abi)
        output_values = parser.parse(abi.outputs, output_values)
        if issubclass(type(output_values), Struct):
            return (output_values,)

        elif returns_array(abi):
            return ([o for o in output_values[0]],)

        else:
            return tuple(output_values)

    def _decode_primitive_value(
        self, value: Any, output_type: Union[str, Tuple, List]
    ) -> Union[str, HexBytes, Tuple]:
        if output_type == "address":
            try:
                return self.decode_address(value)
            except InsufficientDataBytes as err:
                raise DecodingError() from err

        elif isinstance(value, bytes):
            return HexBytes(value)

        elif isinstance(output_type, str) and is_array(output_type):
            sub_type = output_type.split("[")[0]
            return tuple([self._decode_primitive_value(v, sub_type) for v in value])

        elif isinstance(output_type, tuple):
            return tuple([self._decode_primitive_value(v, t) for v, t in zip(value, output_type)])

        elif (
            isinstance(output_type, list)
            and len(output_type) == 1
            and isinstance(value, (list, tuple))
        ):
            return tuple([self._decode_primitive_value(v, output_type[0]) for v in value])

        return value

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
            :class:`~ape.api.transactions.TransactionAPI`
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

    def decode_logs(self, abi: EventABI, data: List[Dict]) -> Iterator["ContractLog"]:
        if not abi.anonymous:
            event_id_bytes = keccak(to_bytes(text=abi.selector))
            matching_logs = [log for log in data if log["topics"][0] == event_id_bytes]
        else:
            matching_logs = data

        topics_list: List[EventABIType] = []
        data_list: List[EventABIType] = []
        for abi_input in abi.inputs:
            if abi_input.indexed:
                topics_list.append(abi_input)
            else:
                data_list.append(abi_input)

        abi_topics = LogInputABICollection(abi, topics_list)
        abi_data = LogInputABICollection(abi, data_list)

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

            def decode_items(abi_types, data):
                def decode_value(t, v) -> Any:
                    if t == "address":
                        return self.decode_address(v)
                    elif t == "bytes32":
                        return HexBytes(v)

                    return v

                return [decode_value(t, v) for t, v in zip(abi_types, data)]

            decoded_topic_data = [
                decode_single(topic_type, topic_data)  # type: ignore
                for topic_type, topic_data in zip(abi_topics.types, indexed_data)
            ]
            decoded_log_data = decode_abi(abi_data.types, log_data)  # type: ignore
            event_args = dict(
                itertools.chain(
                    zip(abi_topics.names, decode_items(abi_topics.types, decoded_topic_data)),
                    zip(abi_data.names, decode_items(abi_data.types, decoded_log_data)),
                )
            )

            yield ContractLog(  # type: ignore
                name=abi.name,
                index=log["logIndex"],
                event_arguments=event_args,
                transaction_hash=log["transactionHash"],
                block_hash=log["blockHash"],
                block_number=log["blockNumber"],
            )  # type: ignore
