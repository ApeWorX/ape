import re
from copy import deepcopy
from decimal import Decimal
from functools import cached_property
from typing import Any, ClassVar, Dict, Iterator, List, Optional, Sequence, Tuple, Type, Union, cast

from eth_abi import decode, encode
from eth_abi.exceptions import InsufficientDataBytes, NonEmptyPaddingBytes
from eth_pydantic_types import HexBytes
from eth_typing import Hash32, HexStr
from eth_utils import (
    encode_hex,
    humanize_hash,
    is_0x_prefixed,
    is_hex,
    is_hex_address,
    keccak,
    to_checksum_address,
)
from ethpm_types import ContractType
from ethpm_types.abi import ABIType, ConstructorABI, EventABI, MethodABI
from pydantic import Field, computed_field, field_validator, model_validator
from pydantic_settings import SettingsConfigDict

from ape.api import BlockAPI, EcosystemAPI, PluginConfig, ReceiptAPI, TransactionAPI
from ape.api.networks import LOCAL_NETWORK_NAME
from ape.contracts.base import ContractCall
from ape.exceptions import (
    ApeException,
    APINotImplementedError,
    ConversionError,
    CustomError,
    DecodingError,
)
from ape.managers.config import merge_configs
from ape.types import (
    AddressType,
    AutoGasLimit,
    CallTreeNode,
    ContractLog,
    GasLimit,
    RawAddress,
    TransactionSignature,
)
from ape.utils import (
    DEFAULT_LIVE_NETWORK_BASE_FEE_MULTIPLIER,
    DEFAULT_LOCAL_TRANSACTION_ACCEPTANCE_TIMEOUT,
    DEFAULT_TRANSACTION_ACCEPTANCE_TIMEOUT,
    EMPTY_BYTES32,
    ZERO_ADDRESS,
    LogInputABICollection,
    Struct,
    StructParser,
    is_array,
    returns_array,
    to_int,
)
from ape.utils.basemodel import _assert_not_ipython_check, only_raise_attribute_error
from ape.utils.misc import DEFAULT_MAX_RETRIES_TX, DEFAULT_TRANSACTION_TYPE
from ape_ethereum.proxies import (
    IMPLEMENTATION_ABI,
    MASTER_COPY_ABI,
    PROXY_TYPE_ABI,
    ProxyInfo,
    ProxyType,
)
from ape_ethereum.transactions import (
    AccessListTransaction,
    BaseTransaction,
    DynamicFeeTransaction,
    Receipt,
    SharedBlobReceipt,
    SharedBlobTransaction,
    StaticFeeTransaction,
    TransactionStatusEnum,
    TransactionType,
)

NETWORKS = {
    # chain_id, network_id
    "mainnet": (1, 1),
    "goerli": (5, 5),
    "sepolia": (11155111, 11155111),
}
BLUEPRINT_HEADER = HexBytes("0xfe71")


class NetworkConfig(PluginConfig):
    required_confirmations: int = 0

    default_provider: Optional[str] = "geth"
    """
    The default provider to use. If set to ``None``, ape will rely on
    an external plugin supplying the provider implementation, such as
    ``ape-hardhat`` supplying forked-network providers.
    """

    block_time: int = 0
    """
    Approximate amount of time for a block to be
    added to the network.
    """

    transaction_acceptance_timeout: int = DEFAULT_TRANSACTION_ACCEPTANCE_TIMEOUT
    """
    The amount tof time before failing when sending a
    transaction and it leaving the mempool.
    """

    default_transaction_type: TransactionType = TransactionType.DYNAMIC
    """
    The default type of transaction to use.
    """

    max_receipt_retries: int = DEFAULT_MAX_RETRIES_TX
    """
    Maximum number of retries when getting a receipt
    from a transaction before failing.
    """

    gas_limit: GasLimit = "auto"
    """
    The gas limit override to use for the network. If set to ``"auto"``, ape will
    estimate gas limits based on the transaction. If set to ``"max"`` the gas limit
    will be set to the maximum block gas limit for the network. Otherwise an ``int``
    can be used to specify an explicit gas limit amount (either base 10 or 16).

    The default for local networks is ``"max"``, otherwise ``"auto"``.
    """

    base_fee_multiplier: float = 1.0
    """A multiplier to apply to a transaction base fee."""

    @field_validator("gas_limit", mode="before")
    @classmethod
    def validate_gas_limit(cls, value):
        if isinstance(value, dict) and "auto" in value:
            return AutoGasLimit.model_validate(value["auto"])

        elif value in ("auto", "max") or isinstance(value, AutoGasLimit):
            return value

        elif isinstance(value, int):
            return value

        elif isinstance(value, str) and value.isnumeric():
            return int(value)

        elif isinstance(value, str) and is_hex(value) and is_0x_prefixed(value):
            return to_int(HexBytes(value))

        elif is_hex(value):
            raise ValueError("Gas limit hex str must include '0x' prefix.")

        raise ValueError(f"Invalid gas limit '{value}'")


class ForkedNetworkConfig(NetworkConfig):
    upstream_provider: Optional[str] = None
    """
    The provider to use as the upstream-provider for this forked network.
    """


def create_local_network_config(
    default_provider: Optional[str] = None, use_fork: bool = False, **kwargs
):
    if "gas_limit" not in kwargs:
        kwargs["gas_limit"] = "max"

    return create_network_config(
        base_fee_multiplier=1.0,
        default_provider=default_provider,
        required_confirmations=0,
        transaction_acceptance_timeout=DEFAULT_LOCAL_TRANSACTION_ACCEPTANCE_TIMEOUT,
        cls=ForkedNetworkConfig if use_fork else NetworkConfig,
        **kwargs,
    )


def create_network_config(
    required_confirmations: int = 2,
    base_fee_multiplier: float = DEFAULT_LIVE_NETWORK_BASE_FEE_MULTIPLIER,
    cls: Type = NetworkConfig,
    **kwargs,
) -> NetworkConfig:
    return cls(
        base_fee_multiplier=base_fee_multiplier,
        required_confirmations=required_confirmations,
        **kwargs,
    )


class BaseEthereumConfig(PluginConfig):
    """
    L2 plugins should use this as their config base-class.
    """

    DEFAULT_TRANSACTION_TYPE: ClassVar[int] = TransactionType.DYNAMIC.value
    DEFAULT_LOCAL_GAS_LIMIT: ClassVar[GasLimit] = "max"
    NETWORKS: ClassVar[Dict[str, Tuple[int, int]]] = NETWORKS

    default_network: str = LOCAL_NETWORK_NAME
    _forked_configs: Dict[str, ForkedNetworkConfig] = {}
    _custom_networks: Dict[str, NetworkConfig] = {}

    model_config = SettingsConfigDict(extra="allow")

    @model_validator(mode="before")
    @classmethod
    def load_network_configs(cls, values):
        cfg_forks: Dict[str, ForkedNetworkConfig] = {}
        custom_networks = {}
        for name, obj in values.items():
            if name.startswith("_"):
                continue

            net_name = name.replace("-", "_")
            key = net_name.replace("_fork", "")
            if net_name.endswith("_fork"):
                key = net_name.replace("_fork", "")
                default_fork_model = create_local_network_config(
                    use_fork=True,
                    default_transaction_type=cls.DEFAULT_TRANSACTION_TYPE,
                    gas_limit=cls.DEFAULT_LOCAL_GAS_LIMIT,
                ).model_dump(by_alias=True)
                data = merge_configs(default_fork_model, obj)
                cfg_forks[key] = ForkedNetworkConfig.model_validate(data)

            elif key != LOCAL_NETWORK_NAME and key not in cls.NETWORKS and isinstance(obj, dict):
                # Custom network.
                default_network_model = create_network_config(
                    default_transaction_type=cls.DEFAULT_TRANSACTION_TYPE
                ).model_dump(by_alias=True)
                data = merge_configs(default_network_model, obj)
                custom_networks[name] = NetworkConfig.model_validate(data)

        values["_forked_configs"] = {**cfg_forks, **values.get("_forked_configs", {})}
        return {**values, **custom_networks}

    @computed_field  # type: ignore[misc]
    @cached_property
    def local(self) -> NetworkConfig:
        return create_local_network_config(
            default_provider="test",
            default_transaction_type=self.DEFAULT_TRANSACTION_TYPE,
            gas_limit=self.DEFAULT_LOCAL_GAS_LIMIT,
        )

    @only_raise_attribute_error
    def __getattr__(self, key: str) -> Any:
        _assert_not_ipython_check(key)
        net_key = key.replace("-", "_")
        if net_key.endswith("_fork"):
            return self._get_forked_config(net_key)

        try:
            return super().__getattr__(key)
        except AttributeError:
            return NetworkConfig(default_transaction_type=self.DEFAULT_TRANSACTION_TYPE)

    def __contains__(self, key: str) -> bool:
        net_key = key.replace("-", "_")
        if net_key.endswith("_fork"):
            return self._get_forked_config(net_key) is not None

        return super().__contains__(key)

    def get(self, key: str, default: Optional[Any] = None) -> Any:
        net_key = key.replace("-", "_")
        if net_key.endswith("_fork"):
            if cfg := self._get_forked_config(net_key):
                return cfg

        result: Any
        if result := super().get(key, default=default):
            return result

        # Handle weird base-class differences.
        try:
            return self.__getattr__(key)
        except AttributeError:
            return default

    def _get_forked_config(self, name: str) -> Optional[ForkedNetworkConfig]:
        live_key: str = name.replace("_fork", "")
        if live_key in self._forked_configs and self._forked_configs[live_key]:
            return self._forked_configs[live_key]

        live_cfg: Any
        if live_cfg := self.get(live_key):
            if isinstance(live_cfg, NetworkConfig):
                fork_cfg = create_local_network_config(
                    use_fork=True,
                    default_transaction_type=self.DEFAULT_TRANSACTION_TYPE,
                    gas_limit=self.DEFAULT_LOCAL_GAS_LIMIT,
                )
                self._forked_configs[live_key] = fork_cfg
                return fork_cfg

        return None

    def _get_custom_network(self, name: str) -> NetworkConfig:
        return self._custom_networks.get(name, NetworkConfig())


class EthereumConfig(BaseEthereumConfig):
    mainnet: NetworkConfig = create_network_config(block_time=13)
    goerli: NetworkConfig = create_network_config(block_time=15)
    sepolia: NetworkConfig = create_network_config(block_time=15)


class Block(BlockAPI):
    """
    Class for representing a block on a chain.
    """

    gas_limit: int = Field(alias="gasLimit")
    gas_used: int = Field(alias="gasUsed")
    base_fee: int = Field(0, alias="baseFeePerGas")
    difficulty: int = 0
    total_difficulty: int = Field(0, alias="totalDifficulty")

    # Type re-declares.
    hash: Optional[HexBytes] = None
    parent_hash: HexBytes = Field(
        EMPTY_BYTES32, alias="parentHash"
    )  # NOTE: genesis block has no parent hash

    @field_validator(
        "base_fee",
        "difficulty",
        "gas_limit",
        "gas_used",
        "number",
        "size",
        "timestamp",
        "total_difficulty",
        mode="before",
    )
    @classmethod
    def validate_ints(cls, value):
        return to_int(value) if value else 0


class Ethereum(EcosystemAPI):
    # NOTE: `default_transaction_type` should be overridden
    #   if the chain doesn't support EIP-1559.

    name: str = "ethereum"
    fee_token_symbol: str = "ETH"

    @property
    def config(self) -> EthereumConfig:
        return cast(EthereumConfig, self.config_manager.get_config(self.name))

    @property
    def default_transaction_type(self) -> TransactionType:
        if provider := self.network_manager.active_provider:
            # Check connected network first.
            networks_to_check = [provider.network.name, self.default_network_name]
        else:
            networks_to_check = [self.default_network_name]

        for name in networks_to_check:
            network = self.get_network(name)
            ecosystem_config = network.config
            ecosystem_default = ecosystem_config.get(
                "default_transaction_type", DEFAULT_TRANSACTION_TYPE
            )
            result: int = network._network_config.get("default_transaction_type", ecosystem_default)
            return TransactionType(result)

        return TransactionType(DEFAULT_TRANSACTION_TYPE)

    @classmethod
    def decode_address(cls, raw_address: RawAddress) -> AddressType:
        return to_checksum_address(HexBytes(raw_address)[-20:].rjust(20, b"\x00"))

    @classmethod
    def encode_address(cls, address: AddressType) -> RawAddress:
        return str(address)

    def decode_transaction_type(self, transaction_type_id: Any) -> Type[TransactionAPI]:
        if isinstance(transaction_type_id, TransactionType):
            tx_type = transaction_type_id
        elif isinstance(transaction_type_id, int):
            tx_type = TransactionType(transaction_type_id)
        else:
            # Using hex or alike.
            tx_type = self.conversion_manager.convert(transaction_type_id, int)

        if tx_type is TransactionType.STATIC:
            return StaticFeeTransaction
        elif tx_type is TransactionType.ACCESS_LIST:
            return AccessListTransaction

        return DynamicFeeTransaction

    def encode_contract_blueprint(
        self, contract_type: ContractType, *args, **kwargs
    ) -> TransactionAPI:
        # EIP-5202 implementation.
        bytes_obj = contract_type.deployment_bytecode
        contract_bytes = (bytes_obj.to_bytes() or b"") if bytes_obj else b""
        header = kwargs.pop("header", BLUEPRINT_HEADER)
        blueprint_bytecode = header + HexBytes(0) + contract_bytes
        len_bytes = len(blueprint_bytecode).to_bytes(2, "big")
        return_data_size = kwargs.pop("return_data_size", HexBytes("0x61"))
        return_instructions = kwargs.pop("return_instructions", HexBytes("0x3d81600a3d39f3"))
        deploy_bytecode = HexBytes(
            return_data_size + len_bytes + return_instructions + blueprint_bytecode
        )
        converted_kwargs = self.conversion_manager.convert_method_kwargs(kwargs)
        return self.encode_deployment(
            deploy_bytecode, contract_type.constructor, **converted_kwargs
        )

    def get_proxy_info(self, address: AddressType) -> Optional[ProxyInfo]:
        contract_code = self.provider.get_code(address)
        if isinstance(contract_code, bytes):
            contract_code = contract_code.hex()

        code = contract_code[2:]
        if not code:
            return None

        patterns = {
            ProxyType.Minimal: r"^363d3d373d3d3d363d73(.{40})5af43d82803e903d91602b57fd5bf3",
            ProxyType.ZeroAge: r"^3d3d3d3d363d3d37363d73(.{40})5af43d3d93803e602a57fd5bf3",
            ProxyType.Clones: r"^36603057343d52307f830d2d700a97af574b186c80d40429385d24241565b08a7c559ba283a964d9b160203da23d3df35b3d3d3d3d363d3d37363d73(.{40})5af43d3d93803e605b57fd5bf3",  # noqa: E501
            ProxyType.Vyper: r"^366000600037611000600036600073(.{40})5af4602c57600080fd5b6110006000f3",  # noqa: E501
            ProxyType.VyperBeta: r"^366000600037611000600036600073(.{40})5af41558576110006000f3",
            ProxyType.CWIA: r"^3d3d3d3d363d3d3761.{4}603736393661.{4}013d73(.{40})5af43d3d93803e603557fd5bf3.*",  # noqa: E501
            ProxyType.OldCWIA: r"^363d3d3761.{4}603836393d3d3d3661.{4}013d73(.{40})5af43d82803e903d91603657fd5bf3.*",  # noqa: E501
            ProxyType.SudoswapCWIA: r"^3d3d3d3d363d3d37605160353639366051013d73(.{40})5af43d3d93803e603357fd5bf3.*",  # noqa: E501
            ProxyType.SoladyCWIA: r"36602c57343d527f9e4ac34f21c619cefc926c8bd93b54bf5a39c7ab2127a895af1cc0691d7e3dff593da1005b363d3d373d3d3d3d61.{4}806062363936013d73(.{40})5af43d3d93803e606057fd5bf3.*",  # noqa: E501
            ProxyType.SplitsCWIA: r"36602f57343d527f9e4ac34f21c619cefc926c8bd93b54bf5a39c7ab2127a895af1cc0691d7e3dff60203da13d3df35b3d3d3d3d363d3d3761.{4}606736393661.{4}013d73(.{40})5af43d3d93803e606557fd5bf3.*",  # noqa: E501
            ProxyType.SoladyPush0: r"^5f5f365f5f37365f73(.{40})5af43d5f5f3e6029573d5ffd5b3d5ff3",
        }
        for type_, pattern in patterns.items():
            if match := re.match(pattern, code):
                target = self.conversion_manager.convert(match.group(1), AddressType)
                return ProxyInfo(type=type_, target=target)

        sequence_pattern = r"363d3d373d3d3d363d30545af43d82803e903d91601857fd5bf3"
        if re.match(sequence_pattern, code):
            # the implementation is stored in the slot matching proxy address
            slot = self.provider.get_storage(address, address)
            target = self.conversion_manager.convert(slot[-20:], AddressType)
            return ProxyInfo(type=ProxyType.Sequence, target=target)

        def str_to_slot(text):
            return int(keccak(text=text).hex(), 16)

        slots = {
            ProxyType.Standard: str_to_slot("eip1967.proxy.implementation") - 1,
            ProxyType.Beacon: str_to_slot("eip1967.proxy.beacon") - 1,
            ProxyType.OpenZeppelin: str_to_slot("org.zeppelinos.proxy.implementation"),
            ProxyType.UUPS: str_to_slot("PROXIABLE"),
        }
        for _type, slot in slots.items():
            try:
                # TODO perf: use a batch call here when ape adds support
                storage = self.provider.get_storage(address, slot)
            except APINotImplementedError:
                continue

            if sum(storage) == 0:
                continue

            target = self.conversion_manager.convert(storage[-20:], AddressType)
            # read `target.implementation()`
            if _type == ProxyType.Beacon:
                target = ContractCall(IMPLEMENTATION_ABI, target)(skip_trace=True)

            return ProxyInfo(type=_type, target=target)

        # safe >=1.1.0 provides `masterCopy()`, which is also stored in slot 0
        # detect safe-specific bytecode of push32 keccak256("masterCopy()")
        safe_pattern = b"\x7f" + keccak(text="masterCopy()")[:4] + bytes(28)
        if safe_pattern.hex() in code:
            try:
                singleton = ContractCall(MASTER_COPY_ABI, address)(skip_trace=True)
                slot_0 = self.provider.get_storage(address, 0)
                target = self.conversion_manager.convert(slot_0[-20:], AddressType)
                # NOTE: `target` is set in initialized proxies
                if target != ZERO_ADDRESS and target == singleton:
                    return ProxyInfo(type=ProxyType.GnosisSafe, target=target)
            except ApeException:
                pass

        # eip-897 delegate proxy, read `proxyType()` and `implementation()`
        # perf: only make a call when a proxyType() selector is mentioned in the code
        eip897_pattern = b"\x63" + keccak(text="proxyType()")[:4]
        if eip897_pattern.hex() in code:
            try:
                proxy_type = ContractCall(PROXY_TYPE_ABI, address)(skip_trace=True)
                if proxy_type not in (1, 2):
                    raise ValueError(f"ProxyType '{proxy_type}' not permitted by EIP-897.")

                target = ContractCall(IMPLEMENTATION_ABI, address)(skip_trace=True)
                # avoid recursion
                if target != ZERO_ADDRESS:
                    return ProxyInfo(type=ProxyType.Delegate, target=target)

            except (ApeException, ValueError):
                pass

        return None

    def decode_receipt(self, data: Dict) -> ReceiptAPI:
        status = data.get("status")
        if status is not None:
            status = self.conversion_manager.convert(status, int)
            status = TransactionStatusEnum(status)

        txn_hash = None
        hash_key_choices = ("hash", "txHash", "txnHash", "transactionHash", "transaction_hash")
        for choice in hash_key_choices:
            if choice in data:
                txn_hash = data[choice]
                break

        if txn_hash:
            txn_hash = txn_hash.hex() if isinstance(txn_hash, bytes) else txn_hash

        data_bytes = data.get("data", b"")
        if data_bytes and isinstance(data_bytes, str):
            data["data"] = HexBytes(data_bytes)

        elif "input" in data and isinstance(data["input"], str):
            data["input"] = HexBytes(data["input"])

        block_number = data.get("block_number", data.get("blockNumber"))
        if block_number is None:
            raise ValueError("Missing block number.")

        receipt_kwargs = dict(
            block_number=block_number,
            contract_address=data.get("contract_address") or data.get("contractAddress"),
            gas_limit=data.get("gas", data.get("gas_limit", data.get("gasLimit"))) or 0,
            gas_price=data.get("gas_price", data.get("gasPrice")) or 0,
            gas_used=data.get("gas_used", data.get("gasUsed")) or 0,
            logs=data.get("logs", []),
            status=status,
            txn_hash=txn_hash,
            transaction=self.create_transaction(**data),
        )

        receipt_cls: Type[Receipt]
        if any(
            x in data
            for x in ("blobGasPrice", "blobGasUsed", "blobVersionedHashes", "maxFeePerBlobGas")
        ):
            receipt_cls = SharedBlobReceipt
            receipt_kwargs["blob_gas_price"] = data.get("blob_gas_price", data.get("blobGasPrice"))
            receipt_kwargs["blob_gas_used"] = data.get("blob_gas_used", data.get("blobGasUsed"))
        else:
            receipt_cls = Receipt

        return receipt_cls.model_validate(receipt_kwargs)

    def decode_block(self, data: Dict) -> BlockAPI:
        data["hash"] = HexBytes(data["hash"]) if data.get("hash") else None
        if "gas_limit" in data:
            data["gasLimit"] = data.pop("gas_limit")
        if "gas_used" in data:
            data["gasUsed"] = data.pop("gas_used")
        if "parent_hash" in data:
            data["parentHash"] = HexBytes(data.pop("parent_hash"))
        if "transaction_ids" in data:
            data["transactions"] = data.pop("transaction_ids")
        if "total_difficulty" in data:
            data["totalDifficulty"] = data.pop("total_difficulty")
        if "base_fee" in data:
            data["baseFeePerGas"] = data.pop("base_fee")
        elif "baseFee" in data:
            data["baseFeePerGas"] = data.pop("baseFee")
        if "transactions" in data:
            data["num_transactions"] = len(data["transactions"])

        if "size" not in data:
            # NOTE: Due to an issue with `eth_subscribe:newHeads` on Infura
            # https://github.com/ApeWorX/ape-infura/issues/72
            data["size"] = -1  # HACK: use an unrealistic sentinel value

        return Block.model_validate(data)

    def _python_type_for_abi_type(self, abi_type: ABIType) -> Union[Type, Sequence]:
        # NOTE: An array can be an array of tuples, so we start with an array check
        if str(abi_type.type).endswith("]"):
            # remove one layer of the potential onion of array
            new_type = "[".join(str(abi_type.type).split("[")[:-1])
            # create a new type with the inner type of array
            new_abi_type = ABIType(type=new_type, **abi_type.model_dump(exclude={"type"}))
            # NOTE: type for static and dynamic array is a single item list
            # containing the type of the array
            return [self._python_type_for_abi_type(new_abi_type)]

        if abi_type.components is not None:
            return tuple(self._python_type_for_abi_type(c) for c in abi_type.components)

        if abi_type.type == "address":
            return AddressType

        elif abi_type.type == "bool":
            return bool

        elif abi_type.type == "string":
            return str

        elif "bytes" in abi_type.type:
            return bytes

        elif "int" in abi_type.type:
            return int

        elif "fixed" in abi_type.type:
            return Decimal

        raise ConversionError(f"Unable to convert '{abi_type}'.")

    def encode_calldata(self, abi: Union[ConstructorABI, MethodABI], *args) -> HexBytes:
        if not abi.inputs:
            return HexBytes("")

        parser = StructParser(abi)
        arguments = parser.encode_input(args)
        input_types = [i.canonical_type for i in abi.inputs]
        python_types = tuple(self._python_type_for_abi_type(i) for i in abi.inputs)
        converted_args = self.conversion_manager.convert(arguments, python_types)
        encoded_calldata = encode(input_types, converted_args)
        return HexBytes(encoded_calldata)

    def decode_calldata(self, abi: Union[ConstructorABI, MethodABI], calldata: bytes) -> Dict:
        raw_input_types = [i.canonical_type for i in abi.inputs]
        input_types = [parse_type(i.model_dump()) for i in abi.inputs]

        try:
            raw_input_values = decode(raw_input_types, calldata, strict=False)
        except InsufficientDataBytes as err:
            raise DecodingError(str(err)) from err

        input_values = [
            self.decode_primitive_value(v, t) for v, t in zip(raw_input_values, input_types)
        ]
        arguments = {}
        index = 0
        for i, v in zip(abi.inputs, input_values):
            name = i.name or f"{index}"
            arguments[name] = v
            index += 1

        return arguments

    def decode_returndata(self, abi: MethodABI, raw_data: bytes) -> Tuple[Any, ...]:
        output_types_str_ls = [o.canonical_type for o in abi.outputs]

        if raw_data:
            try:
                vm_return_values = decode(output_types_str_ls, raw_data, strict=False)
            except (InsufficientDataBytes, NonEmptyPaddingBytes) as err:
                raise DecodingError(str(err)) from err
        else:
            # Use all zeroes.
            vm_return_values = tuple([0 for _ in output_types_str_ls])

        if not vm_return_values:
            return vm_return_values

        elif not isinstance(vm_return_values, (tuple, list)):
            vm_return_values = (vm_return_values,)

        output_types = [parse_type(o.model_dump()) for o in abi.outputs]
        output_values = [
            self.decode_primitive_value(v, t) for v, t in zip(vm_return_values, output_types)
        ]
        parser = StructParser(abi)
        output_values = parser.decode_output(output_values)

        if issubclass(type(output_values), Struct):
            return (output_values,)

        elif (
            returns_array(abi)
            and isinstance(output_values, (list, tuple))
            and len(output_values) == 1
        ):
            # Array of structs or tuples: don't convert to list
            # Array of anything else: convert to single list
            return (
                (
                    [
                        output_values[0],
                    ],
                )
                if issubclass(type(output_values[0]), Struct)
                else ([o for o in output_values[0]],)
            )

        elif returns_array(abi):
            # Tuple with single item as the array.
            return (output_values,)

        return tuple(output_values)

    def _enrich_value(self, value: Any, **kwargs) -> Any:
        if isinstance(value, bytes):
            try:
                string_value = value.strip(b"\x00").decode("utf8")
                return f'"{string_value}"'
            except UnicodeDecodeError:
                # Truncate bytes if very long.
                if len(value) > 24:
                    return humanize_hash(cast(Hash32, value))

                hex_str = HexBytes(value).hex()
                if is_hex_address(hex_str):
                    return self._enrich_value(hex_str, **kwargs)

                return hex_str

        elif isinstance(value, str) and is_hex_address(value):
            address = self.decode_address(value)
            return self._enrich_address(address, **kwargs)

        elif isinstance(value, str):
            # Surround non-address strings with quotes.
            return f'"{value}"'

        elif isinstance(value, (list, tuple)):
            return [self._enrich_value(v, **kwargs) for v in value]

        elif isinstance(value, Struct):
            return {k: self._enrich_value(v, **kwargs) for k, v in value.items()}

        return value

    def decode_primitive_value(
        self, value: Any, output_type: Union[str, Tuple, List]
    ) -> Union[str, HexBytes, Tuple, List]:
        if output_type == "address":
            try:
                return self.decode_address(value)
            except InsufficientDataBytes as err:
                raise DecodingError() from err

        elif isinstance(value, bytes):
            return HexBytes(value)

        elif isinstance(output_type, str) and is_array(output_type):
            sub_type = "[".join(output_type.split("[")[:-1])
            return [self.decode_primitive_value(v, sub_type) for v in value]

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
        data = HexBytes(deployment_bytecode)

        # Encode args, if there are any
        if abi and args:
            data = HexBytes(data + self.encode_calldata(abi, *args))

        txn.data = data
        return cast(BaseTransaction, txn)

    def encode_transaction(
        self,
        address: AddressType,
        abi: MethodABI,
        *args,
        **kwargs,
    ) -> BaseTransaction:
        txn = self.create_transaction(receiver=address, **kwargs)

        # Add method ID
        txn.data = self.get_method_selector(abi)
        txn.data = HexBytes(txn.data + self.encode_calldata(abi, *args))

        return cast(BaseTransaction, txn)

    def create_transaction(self, **kwargs) -> TransactionAPI:
        """
        Returns a transaction using the given constructor kwargs.

        **NOTE**: This generally should not be called by the user since this API method is used as a
        hook for Ecosystems to customize how transactions are created.

        Returns:
            :class:`~ape.api.transactions.TransactionAPI`
        """

        # Handle all aliases.
        tx_data = dict(kwargs)
        tx_data = _correct_key(
            "max_priority_fee",
            tx_data,
            ("max_priority_fee_per_gas", "maxPriorityFeePerGas", "maxPriorityFee"),
        )
        tx_data = _correct_key("max_fee", tx_data, ("max_fee_per_gas", "maxFeePerGas", "maxFee"))
        tx_data = _correct_key("gas", tx_data, ("gas_limit", "gasLimit"))
        tx_data = _correct_key("gas_price", tx_data, ("gasPrice",))
        tx_data = _correct_key(
            "type",
            tx_data,
            ("txType", "tx_type", "txnType", "txn_type", "transactionType", "transaction_type"),
        )
        tx_data = _correct_key("maxFeePerBlobGas", tx_data, ("max_fee_per_blob_gas",))
        tx_data = _correct_key("blobVersionedHashes", tx_data, ("blob_versioned_hashes",))

        # Handle unique value specifications, such as "1 ether".
        if "value" in tx_data and not isinstance(tx_data["value"], int):
            value = tx_data["value"] or 0  # Convert None to 0.
            tx_data["value"] = self.conversion_manager.convert(value, int)

        # None is not allowed, the user likely means `b""`.
        if "data" in tx_data and tx_data["data"] is None:
            tx_data["data"] = b""

        # Deduce the transaction type.
        transaction_types: Dict[TransactionType, Type[TransactionAPI]] = {
            TransactionType.STATIC: StaticFeeTransaction,
            TransactionType.ACCESS_LIST: AccessListTransaction,
            TransactionType.DYNAMIC: DynamicFeeTransaction,
            TransactionType.SHARED_BLOB: SharedBlobTransaction,
        }
        if "type" in tx_data:
            # May be None in data.
            if tx_data["type"] is None:
                # Explicit `None` means used default.
                version = self.default_transaction_type
            elif isinstance(tx_data["type"], TransactionType):
                version = tx_data["type"]
            elif isinstance(tx_data["type"], int):
                version = TransactionType(tx_data["type"])
            else:
                # Using hex values or alike.
                version = TransactionType(self.conversion_manager.convert(tx_data["type"], int))

        elif "gas_price" in tx_data:
            version = TransactionType.STATIC
        elif "max_fee" in tx_data or "max_priority_fee" in tx_data:
            version = TransactionType.DYNAMIC
        elif "access_list" in tx_data or "accessList" in tx_data:
            version = TransactionType.ACCESS_LIST
        elif "maxFeePerBlobGas" in tx_data or "blobVersionedHashes" in tx_data:
            version = TransactionType.SHARED_BLOB
        else:
            version = self.default_transaction_type

        tx_data["type"] = version.value

        # This causes problems in pydantic for some reason.
        # NOTE: This must happen after deducing the tx type!
        if "gas_price" in tx_data and tx_data["gas_price"] is None:
            del tx_data["gas_price"]

        txn_class = transaction_types[version]

        if "required_confirmations" not in tx_data or tx_data["required_confirmations"] is None:
            # Attempt to use default required-confirmations from `ape-config.yaml`.
            required_confirmations = 0
            active_provider = self.network_manager.active_provider
            if active_provider:
                required_confirmations = active_provider.network.required_confirmations

            tx_data["required_confirmations"] = required_confirmations

        if isinstance(tx_data.get("chainId"), str):
            tx_data["chainId"] = int(tx_data["chainId"], 16)

        elif (
            "chainId" not in tx_data or tx_data["chainId"] is None
        ) and self.network_manager.active_provider is not None:
            tx_data["chainId"] = self.provider.chain_id

        if "input" in tx_data:
            tx_data["data"] = tx_data.pop("input")

        if all(field in tx_data for field in ("v", "r", "s")):
            tx_data["signature"] = TransactionSignature(
                v=tx_data["v"],
                r=bytes(tx_data["r"]),
                s=bytes(tx_data["s"]),
            )

        if "gas" not in tx_data:
            tx_data["gas"] = None

        return txn_class(**tx_data)

    def decode_logs(self, logs: Sequence[Dict], *events: EventABI) -> Iterator["ContractLog"]:
        if not logs:
            return

        abi_inputs = {
            encode_hex(keccak(text=abi.selector)): LogInputABICollection(abi) for abi in events
        }

        def get_abi(_topic: HexStr) -> Optional[LogInputABICollection]:
            return abi_inputs[_topic] if _topic in abi_inputs else None

        for log in logs:
            if log.get("anonymous"):
                raise NotImplementedError(
                    "decoding anonymous logs is not supported with this method"
                )
            topics = log["topics"]
            # web3.py converts topics to HexBytes, data is always a HexStr
            if isinstance(log["topics"][0], bytes):
                topics = [encode_hex(t) for t in log["topics"]]

            elif not topics:
                continue

            if not (abi := get_abi(topics[0])):
                continue

            event_arguments = abi.decode(topics, log["data"], use_hex_on_fail=True)

            # Since LogABICollection does not have access to the Ecosystem,
            # the rest of the decoding must happen here.
            converted_arguments: Dict = {}

            for item in abi.abi.inputs:
                _type, key, value = item.canonical_type, item.name, event_arguments[item.name]

                if isinstance(value, Struct):
                    struct_types = _type.lstrip("(").rstrip(")").split(",")
                    for struct_type, (struct_key, struct_val) in zip(struct_types, value.items()):
                        value[struct_key] = (
                            self.decode_address(struct_val)
                            if struct_type == "address"
                            else HexBytes(struct_val) if "bytes" in struct_type else struct_val
                        )
                    converted_arguments[key] = value

                elif _type == "address":
                    converted_arguments[key] = self.decode_address(value)

                elif is_array(_type):
                    sub_type = "[".join(_type.split("[")[:-1])
                    converted_arguments[key] = (
                        [self.decode_address(v) for v in value] if sub_type == "address" else value
                    )

                else:
                    # No change.
                    converted_arguments[key] = value

            yield ContractLog(
                block_hash=log.get("blockHash") or log.get("block_hash") or "",
                block_number=log.get("blockNumber") or log.get("block_number") or 0,
                contract_address=self.decode_address(log["address"]),
                event_arguments=converted_arguments,
                event_name=abi.event_name,
                log_index=log.get("logIndex") or log.get("log_index") or 0,
                transaction_hash=log.get("transactionHash") or log.get("transaction_hash") or "",
                transaction_index=(
                    log.get("transactionIndex")
                    if "transactionIndex" in log
                    else log.get("transaction_index")
                ),
            )

    def enrich_calltree(self, call: CallTreeNode, **kwargs) -> CallTreeNode:
        kwargs["use_symbol_for_tokens"] = kwargs.get("use_symbol_for_tokens", False)
        kwargs["in_place"] = kwargs.get("in_place", True)

        if call.txn_hash:
            receipt = self.chain_manager.get_receipt(call.txn_hash)
            kwargs["sender"] = receipt.sender

        # Enrich subcalls before any _return_ statement.
        enriched_call = call if kwargs["in_place"] else deepcopy(call)
        enriched_call.calls = [self.enrich_calltree(c, **kwargs) for c in enriched_call.calls]

        not_address_type: bool = not self.conversion_manager.is_type(
            enriched_call.contract_id, AddressType
        )
        if not_address_type and is_hex_address(enriched_call.contract_id):
            enriched_call.contract_id = self.decode_address(enriched_call.contract_id)

        elif not_address_type:
            # Already enriched.
            return enriched_call

        # Collapse pre-compile address calls
        address = cast(AddressType, enriched_call.contract_id)
        address_int = int(address, 16)
        if 1 <= address_int <= 9:
            sub_calls = [self.enrich_calltree(c, **kwargs) for c in enriched_call.calls]
            if len(sub_calls) == 1:
                return sub_calls[0]

            intermediary_node = CallTreeNode(contract_id=f"{address_int}")
            for sub_tree in sub_calls:
                intermediary_node.add(sub_tree)

            return intermediary_node

        if not (contract_type := self.chain_manager.contracts.get(address)):
            return enriched_call

        enriched_call.contract_id = self._enrich_address(address, **kwargs)
        method_abi: Optional[Union[MethodABI, ConstructorABI]] = None
        if "CREATE" in (enriched_call.call_type or ""):
            method_abi = contract_type.constructor
            name = "__new__"

        elif enriched_call.method_id is None:
            name = enriched_call.method_id or "0x"

        else:
            method_id_bytes = HexBytes(enriched_call.method_id)
            if method_id_bytes in contract_type.methods:
                method_abi = contract_type.methods[method_id_bytes]
                assert isinstance(method_abi, MethodABI)  # For mypy

                # Check if method name duplicated. If that is the case, use selector.
                times = len([x for x in contract_type.methods if x.name == method_abi.name])
                name = (
                    method_abi.name if times == 1 else method_abi.selector
                ) or enriched_call.method_id
                enriched_call = self._enrich_calldata(
                    enriched_call, method_abi, contract_type, **kwargs
                )
            else:
                name = enriched_call.method_id or "0x"

        enriched_call.method_id = name

        if method_abi:
            enriched_call = self._enrich_calldata(
                enriched_call, method_abi, contract_type, **kwargs
            )

            if isinstance(method_abi, MethodABI):
                enriched_call = self._enrich_returndata(enriched_call, method_abi, **kwargs)
            else:
                # For constructors, don't include outputs, as it is likely a large amount of bytes.
                enriched_call.outputs = None

        return enriched_call

    def _enrich_address(self, address: AddressType, **kwargs) -> str:
        if address and address == kwargs.get("sender"):
            return "tx.origin"

        elif address == ZERO_ADDRESS:
            return "ZERO_ADDRESS"

        if not (contract_type := self.chain_manager.contracts.get(address)):
            return address

        elif kwargs.get("use_symbol_for_tokens") and "symbol" in contract_type.view_methods:
            # Use token symbol as name
            contract = self.chain_manager.contracts.instance_at(
                address, contract_type=contract_type
            )

            try:
                symbol = contract.symbol(skip_trace=True)
            except ApeException:
                symbol = None

            if isinstance(symbol, str):
                return symbol.strip()

            # bytes32 symbol appears in ds-token
            if isinstance(symbol, bytes):
                try:
                    return symbol.rstrip(b"\x00").decode()
                except UnicodeDecodeError:
                    return str(symbol)

        name = contract_type.name.strip() if contract_type.name else None
        return name or self._get_contract_id_from_address(address)

    def _get_contract_id_from_address(self, address: "AddressType") -> str:
        if address in self.account_manager:
            return f"Transferring {self.fee_token_symbol}"

        return address

    def _enrich_calldata(
        self,
        call: CallTreeNode,
        method_abi: Union[MethodABI, ConstructorABI],
        contract_type: ContractType,
        **kwargs,
    ) -> CallTreeNode:
        calldata = call.inputs
        if isinstance(calldata, (str, bytes, int)):
            calldata_arg = HexBytes(calldata)
        else:
            # Not sure if we can get here.
            # Mostly for mypy's sake.
            return call

        if call.call_type and "CREATE" in call.call_type:
            # Strip off bytecode
            bytecode = (
                contract_type.deployment_bytecode.to_bytes()
                if contract_type.deployment_bytecode
                else b""
            )
            # TODO: Handle Solidity Metadata (delegate to Compilers again?)
            calldata_arg = HexBytes(calldata_arg.split(bytecode)[-1])

        try:
            call.inputs = self.decode_calldata(method_abi, calldata_arg)
        except DecodingError:
            call.inputs = ["<?>" for _ in method_abi.inputs]
        else:
            call.inputs = {k: self._enrich_value(v, **kwargs) for k, v in call.inputs.items()}

        return call

    def _enrich_returndata(
        self, call: CallTreeNode, method_abi: MethodABI, **kwargs
    ) -> CallTreeNode:
        if call.call_type and "CREATE" in call.call_type:
            call.outputs = ""
            return call

        default_return_value = "<?>"
        if (isinstance(call.outputs, str) and is_0x_prefixed(call.outputs)) or isinstance(
            call.outputs, (int, bytes)
        ):
            return_value_bytes = HexBytes(call.outputs)
        else:
            return_value_bytes = None

        if return_value_bytes is None:
            values = tuple([default_return_value for _ in method_abi.outputs])

        else:
            return_values = None
            try:
                return_values = (
                    self.decode_returndata(method_abi, return_value_bytes)
                    if not call.failed
                    else None
                )
            except DecodingError:
                if return_value_bytes == HexBytes("0x"):
                    # Empty result, but it failed decoding because of its length.
                    return_values = ("",)

            values = (
                tuple([default_return_value for _ in method_abi.outputs])
                if return_values is None
                else tuple([self._enrich_value(v, **kwargs) for v in return_values or ()])
            )

        output_val = values[0] if len(values) == 1 else values
        if (
            isinstance(output_val, str)
            and is_0x_prefixed(output_val)
            and "." not in output_val
            and not int(output_val, 16)
        ):
            output_val = ""

        call.outputs = output_val
        return call

    def get_python_types(self, abi_type: ABIType) -> Union[Type, Sequence]:
        return self._python_type_for_abi_type(abi_type)

    def decode_custom_error(
        self,
        data: HexBytes,
        address: AddressType,
        **kwargs,
    ) -> Optional[CustomError]:
        # Use an instance (required for proper error caching).
        contract = self.chain_manager.contracts.instance_at(address)

        selector = data[:4]
        input_data = data[4:]

        abi = None
        if selector not in contract.contract_type.errors:
            # ABI not found. Try looking at the "last" contract.
            if not (tx := kwargs.get("txn")) or not self.network_manager.active_provider:
                return None
            elif not (last_addr := self._get_last_address_from_trace(tx.txn_hash)):
                return None

            if last_addr == address:
                # Avoid checking same address twice.
                return None

            try:
                if not (cerr := self.decode_custom_error(data, last_addr)):
                    return cerr
            except NotImplementedError:
                return None

            # error never found.
            return None

        abi = contract.contract_type.errors[selector]
        error_cls = contract.get_error_by_signature(abi.signature)
        inputs = self.decode_calldata(abi, input_data)
        kwargs["contract_address"] = address
        return error_cls(abi, inputs, **kwargs)

    def _get_last_address_from_trace(self, txn_hash: Union[str, HexBytes]) -> Optional[AddressType]:
        try:
            trace = list(self.chain_manager.provider.get_transaction_trace(txn_hash))
        except Exception:
            return None

        for frame in trace[::-1]:
            if not (addr := frame.contract_address):
                continue

            return addr

        return None


def parse_type(type_: Dict[str, Any]) -> Union[str, Tuple, List]:
    if "tuple" not in type_["type"]:
        return type_["type"]

    result = tuple([parse_type(c) for c in type_["components"]])
    return [result] if is_array(type_["type"]) else result


def _correct_key(key: str, data: Dict, alt_keys: Tuple[str, ...]) -> Dict:
    if key in data:
        return data

    # Check for alternative.
    for possible_key in alt_keys:
        if possible_key not in data:
            continue

        # Alt found: use it.
        new_data = {k: v for k, v in data.items() if k not in alt_keys}
        new_data[key] = data[possible_key]
        return new_data

    return data
