import itertools
import re
from enum import IntEnum
from typing import Any, Dict, Iterator, List, Optional, Tuple, Union

from eth_abi import decode_abi as abi_decode
from eth_abi import encode_abi as abi_encode
from eth_abi.abi import decode_abi, decode_single
from eth_abi.exceptions import InsufficientDataBytes
from eth_typing import HexStr
from eth_utils import (
    add_0x_prefix,
    decode_hex,
    hexstr_if_str,
    keccak,
    to_bytes,
    to_checksum_address,
)
from ethpm_types.abi import ABIType, ConstructorABI, EventABI, EventABIType, MethodABI
from hexbytes import HexBytes
from pydantic import Field

from ape.api import BlockAPI, EcosystemAPI, PluginConfig, ReceiptAPI, TransactionAPI
from ape.api.networks import LOCAL_NETWORK_NAME, ProxyInfoAPI
from ape.contracts.base import ContractCall
from ape.exceptions import DecodingError, TransactionError
from ape.types import AddressType, ContractLog, RawAddress, TransactionSignature
from ape.utils import (
    LogInputABICollection,
    Struct,
    StructParser,
    is_array,
    parse_type,
    returns_array,
)
from ape_ethereum.transactions import (
    AccessListTransaction,
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


class ProxyType(IntEnum):
    Minimal = 0  # eip-1167 minimal proxy contract
    Standard = 1  # eip-1967 standard proxy storage slots
    Beacon = 2  # eip-1967 beacon proxy
    UUPS = 3  # # eip-1822 universal upgradeable proxy standard
    Vyper = 4  # vyper <0.2.9 create_forwarder_to
    Clones = 5  # 0xsplits clones
    GnosisSafe = 6
    OpenZeppelin = 7  # openzeppelin upgradeability proxy
    Delegate = 8  # eip-897 delegate proxy
    ZeroAge = 9  # a more-minimal proxy


class ProxyInfo(ProxyInfoAPI):
    type: ProxyType


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


class Block(BlockAPI):
    """
    Class for representing a block on a chain.
    """

    gas_limit: int = Field(alias="gasLimit")
    gas_used: int = Field(alias="gasUsed")
    base_fee: Optional[int] = Field(None, alias="baseFeePerGas")
    difficulty: Optional[int] = None
    total_difficulty: Optional[int] = Field(None, alias="totalDifficulty")


class Ethereum(EcosystemAPI):
    default_transaction_type = TransactionType.DYNAMIC
    """
    Default transaction type should be overidden id chain doesn't support EIP-1559
    """

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

    def get_proxy_info(self, address: AddressType) -> Optional[ProxyInfo]:
        code = self.provider.get_code(address).hex()[2:]
        patterns = {
            ProxyType.Minimal: r"363d3d373d3d3d363d73(.{40})5af43d82803e903d91602b57fd5bf3",
            ProxyType.Vyper: r"366000600037611000600036600073(.{40})5af4602c57600080fd5b6110006000f3",  # noqa: E501
            ProxyType.Clones: r"36603057343d52307f830d2d700a97af574b186c80d40429385d24241565b08a7c559ba283a964d9b160203da23d3df35b3d3d3d3d363d3d37363d73(.{40})5af43d3d93803e605b57fd5bf3",  # noqa: E501
            ProxyType.ZeroAge: r"3d3d3d3d363d3d37363d73(.{40})5af43d3d93803e602a57fd5bf3",
        }
        for type, pattern in patterns.items():
            match = re.match(pattern, code)
            if match:
                target = self.conversion_manager.convert(match.group(1), AddressType)
                return ProxyInfo(type=type, target=target)

        str_to_slot = lambda text: int(keccak(text=text).hex(), 16)  # noqa: E731
        slots = {
            ProxyType.Standard: str_to_slot("eip1967.proxy.implementation") - 1,
            ProxyType.Beacon: str_to_slot("eip1967.proxy.beacon") - 1,
            ProxyType.OpenZeppelin: str_to_slot("org.zeppelinos.proxy.implementation"),
            ProxyType.UUPS: str_to_slot("PROXIABLE"),
        }
        for type, slot in slots.items():
            storage = self.provider.get_storage_at(address, slot)
            if sum(storage) == 0:
                continue

            target = self.conversion_manager.convert(storage[-20:].hex(), AddressType)

            # read `target.implementation()`
            if type == ProxyType.Beacon:
                abi = MethodABI(
                    type="function",
                    name="implementation",
                    stateMutability="view",
                    outputs=[ABIType(type="address")],
                )
                target = ContractCall(abi, target)()

            return ProxyInfo(type=type, target=target)

        # gnosis safe stores implementation in slot 0, read `masterCopy()` to be sure
        abi = MethodABI(
            type="function",
            name="masterCopy",
            stateMutability="view",
            outputs=[ABIType(type="address")],
        )
        try:
            master_copy = ContractCall(abi, address)()
            storage = self.provider.get_storage_at(address, 0)
            slot_0 = self.conversion_manager.convert(storage[-20:].hex(), AddressType)
            if master_copy == slot_0:
                return ProxyInfo(type=ProxyType.GnosisSafe, target=master_copy)
        except (DecodingError, TransactionError):
            pass

        # delegate proxy, read `proxyType()` and `implementation()`
        proxy_type_abi = MethodABI(
            type="function",
            name="proxyType",
            stateMutability="view",
            outputs=[ABIType(type="uint256")],
        )
        implementation_abi = MethodABI(
            type="function",
            name="implementation",
            stateMutability="view",
            outputs=[ABIType(type="address")],
        )
        try:
            proxy_type = ContractCall(proxy_type_abi, address)()
            if proxy_type not in (1, 2):
                raise ValueError(f"ProxyType '{proxy_type}' not permitted by EIP-897.")

            target = ContractCall(implementation_abi, address)()
            # avoid recursion
            if target != "0x0000000000000000000000000000000000000000":
                return ProxyInfo(type=ProxyType.Delegate, target=target)

        except (DecodingError, TransactionError, ValueError):
            pass

        return None

    def decode_receipt(self, data: dict) -> ReceiptAPI:
        status = data.get("status")
        if status:
            if isinstance(status, str) and status.isnumeric():
                status = int(status)

            status = TransactionStatusEnum(status)

        txn_hash = data.get("hash")

        if txn_hash:
            txn_hash = data["hash"].hex() if isinstance(data["hash"], HexBytes) else data["hash"]

        input_data = data.get("data") or data.get("input", b"")
        if isinstance(input_data, str):
            input_data = bytes(HexBytes(input_data))

        receipt = Receipt(  # type: ignore
            block_number=data.get("block_number") or data.get("blockNumber"),
            contract_address=data.get("contractAddress"),
            data=data.get("data") or data.get("input", b""),
            gas_limit=data.get("gas") or data.get("gasLimit"),
            gas_price=data.get("gas_price") or data.get("gasPrice"),
            gas_used=data.get("gas_used") or data.get("gasUsed"),
            logs=data.get("logs", []),
            nonce=data["nonce"] if "nonce" in data and data["nonce"] != "" else None,
            provider=data.get("provider"),
            receiver=data.get("to") or data.get("receiver") or "",
            required_confirmations=data.get("required_confirmations", 0),
            sender=data.get("sender") or data.get("from"),
            status=status,
            txn_hash=txn_hash,
            value=data.get("value", 0),
        )
        return receipt

    def decode_block(self, data: Dict) -> BlockAPI:
        if "gas_limit" in data:
            data["gasLimit"] = data.pop("gas_limit")
        if "gas_used" in data:
            data["gasUsed"] = data.pop("gas_used")
        if "parent_hash" in data:
            data["parentHash"] = data.pop("parent_hash")
        if "transaction_ids" in data:
            data["transactions"] = data.pop("transaction_ids")
        if "total_difficulty" in data:
            data["totalDifficulty"] = data.pop("total_difficulty")
        if "base_fee" in data:
            data["baseFee"] = data.pop("base_fee")
        data["num_transactions"] = len(data["transactions"])
        return Block.parse_obj(data)

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

        elif not isinstance(vm_return_values, (tuple, list)):
            vm_return_values = (vm_return_values,)

        output_values = [
            self.decode_primitive_value(v, parse_type(t))
            for v, t in zip(vm_return_values, output_types)
        ]
        parser = StructParser(abi)
        output_values = parser.parse(abi.outputs, output_values)

        if issubclass(type(output_values), Struct):
            return (output_values,)

        elif (
            returns_array(abi)
            and isinstance(output_values, (list, tuple))
            and len(output_values) == 1
        ):
            return ([o for o in output_values[0]],)

        return tuple(output_values)

    def decode_primitive_value(
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
            return tuple([self.decode_primitive_value(v, sub_type) for v in value])

        elif isinstance(output_type, tuple):
            return tuple([self.decode_primitive_value(v, t) for v, t in zip(value, output_type)])

        elif (
            isinstance(output_type, list)
            and len(output_type) == 1
            and isinstance(value, (list, tuple))
        ):
            return tuple([self.decode_primitive_value(v, output_type[0]) for v in value])

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
            TransactionType.ACCESS_LIST: AccessListTransaction,
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
            version = self.default_transaction_type

        txn_class = transaction_types[version]
        kwargs["type"] = version.value

        if "required_confirmations" not in kwargs or kwargs["required_confirmations"] is None:
            # Attempt to use default required-confirmations from `ape-config.yaml`.
            required_confirmations = 0
            active_provider = self.network_manager.active_provider
            if active_provider:
                required_confirmations = active_provider.network.required_confirmations

            kwargs["required_confirmations"] = required_confirmations

        if isinstance(kwargs.get("chainId"), str):
            kwargs["chainId"] = int(kwargs["chainId"], 16)

        if "input" in kwargs:
            kwargs["data"] = decode_hex(kwargs.pop("input"))

        if all(field in kwargs for field in ("v", "r", "s")):
            kwargs["signature"] = TransactionSignature(  # type: ignore
                v=kwargs["v"],
                r=bytes(kwargs["r"]),
                s=bytes(kwargs["s"]),
            )

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

        abi_topics = LogInputABICollection(abi, topics_list, True)
        abi_data = LogInputABICollection(abi, data_list, False)

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
