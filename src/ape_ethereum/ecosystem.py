import re
from copy import deepcopy
from typing import Any, Dict, Iterator, List, Optional, Tuple, Type, Union, cast

from eth_abi import decode, encode
from eth_abi.exceptions import InsufficientDataBytes, NonEmptyPaddingBytes
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
from ethpm_types import ContractType, HexBytes
from ethpm_types.abi import ABIType, ConstructorABI, EventABI, MethodABI

from ape._pydantic_compat import Field, validator
from ape.api import BlockAPI, EcosystemAPI, PluginConfig, ReceiptAPI, TransactionAPI
from ape.api.networks import LOCAL_NETWORK_NAME
from ape.contracts.base import ContractCall
from ape.exceptions import (
    ApeException,
    APINotImplementedError,
    ContractError,
    ConversionError,
    DecodingError,
)
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
from ape.utils.misc import DEFAULT_MAX_RETRIES_TX
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
    transaction_acceptance_timeout: int = DEFAULT_TRANSACTION_ACCEPTANCE_TIMEOUT
    default_transaction_type: TransactionType = TransactionType.DYNAMIC
    max_receipt_retries: int = DEFAULT_MAX_RETRIES_TX

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

    class Config:
        smart_union = True

    @validator("gas_limit", pre=True, allow_reuse=True)
    def validate_gas_limit(cls, value):
        if isinstance(value, dict) and "auto" in value:
            return AutoGasLimit.parse_obj(value["auto"])

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


def _create_local_config(default_provider: Optional[str] = None, use_fork: bool = False, **kwargs):
    return _create_config(
        base_fee_multiplier=1.0,
        default_provider=default_provider,
        gas_limit="max",
        required_confirmations=0,
        transaction_acceptance_timeout=DEFAULT_LOCAL_TRANSACTION_ACCEPTANCE_TIMEOUT,
        cls=ForkedNetworkConfig if use_fork else NetworkConfig,
        **kwargs,
    )


def _create_config(
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


class EthereumConfig(PluginConfig):
    mainnet: NetworkConfig = _create_config(block_time=13)
    mainnet_fork: ForkedNetworkConfig = _create_local_config(use_fork=True)
    goerli: NetworkConfig = _create_config(block_time=15)
    goerli_fork: ForkedNetworkConfig = _create_local_config(use_fork=True)
    sepolia: NetworkConfig = _create_config(block_time=15)
    sepolia_fork: ForkedNetworkConfig = _create_local_config(use_fork=True)
    local: NetworkConfig = _create_local_config(default_provider="test")
    default_network: str = LOCAL_NETWORK_NAME


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

    @validator(
        "base_fee",
        "difficulty",
        "gas_limit",
        "gas_used",
        "number",
        "size",
        "timestamp",
        "total_difficulty",
        pre=True,
    )
    def validate_ints(cls, value):
        return to_int(value) if value else 0


class Ethereum(EcosystemAPI):
    """
    Default transaction type should be overridden id chain doesn't support EIP-1559
    """

    name: str = "ethereum"
    fee_token_symbol: str = "ETH"

    @property
    def config(self) -> EthereumConfig:
        result = self.config_manager.get_config("ethereum")
        assert isinstance(result, EthereumConfig)  # For mypy
        return result

    @property
    def default_transaction_type(self) -> TransactionType:
        network = self.default_network.replace("-", "_")
        return self.config[network].default_transaction_type

    @classmethod
    def decode_address(cls, raw_address: RawAddress) -> AddressType:
        return to_checksum_address(HexBytes(raw_address)[-20:].rjust(20, b"\x00"))

    @classmethod
    def encode_address(cls, address: AddressType) -> RawAddress:
        return str(address)

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
            slot = self.provider.get_storage_at(address, address)
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
                storage = self.provider.get_storage_at(address, slot)
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
                slot_0 = self.provider.get_storage_at(address, 0)
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

    def decode_receipt(self, data: dict) -> ReceiptAPI:
        status = data.get("status")
        if status:
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

        block_number = data.get("block_number") or data.get("blockNumber")
        if block_number is None:
            raise ValueError("Missing block number.")

        receipt = Receipt(
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
        return receipt

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

        return Block.parse_obj(data)

    def _python_type_for_abi_type(self, abi_type: ABIType) -> Union[Type, Tuple, List]:
        # NOTE: An array can be an array of tuples, so we start with an array check
        if str(abi_type.type).endswith("]"):
            # remove one layer of the potential onion of array
            new_type = "[".join(str(abi_type.type).split("[")[:-1])
            # create a new type with the inner type of array
            new_abi_type = ABIType(type=new_type, **abi_type.dict(exclude={"type"}))
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
        input_types = [parse_type(i.dict()) for i in abi.inputs]

        try:
            raw_input_values = decode(raw_input_types, calldata)
            input_values = [
                self.decode_primitive_value(v, t) for v, t in zip(raw_input_values, input_types)
            ]
        except InsufficientDataBytes as err:
            raise DecodingError(str(err)) from err

        arguments = {}
        index = 0
        for i, v in zip(abi.inputs, input_values):
            name = i.name or f"{index}"
            arguments[name] = v
            index += 1

        return arguments

    def decode_returndata(self, abi: MethodABI, raw_data: bytes) -> Tuple[Any, ...]:
        output_types_str_ls = [o.canonical_type for o in abi.outputs]

        try:
            vm_return_values = decode(output_types_str_ls, raw_data)
        except (InsufficientDataBytes, NonEmptyPaddingBytes) as err:
            raise DecodingError(str(err)) from err

        if not vm_return_values:
            return vm_return_values

        elif not isinstance(vm_return_values, (tuple, list)):
            vm_return_values = (vm_return_values,)

        output_types = [parse_type(o.dict()) for o in abi.outputs]
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
            return ([o for o in output_values[0]],)

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

        transaction_types: Dict[TransactionType, Type[TransactionAPI]] = {
            TransactionType.STATIC: StaticFeeTransaction,
            TransactionType.DYNAMIC: DynamicFeeTransaction,
            TransactionType.ACCESS_LIST: AccessListTransaction,
        }

        if "type" in kwargs:
            if kwargs["type"] is None:
                version = TransactionType.DYNAMIC
            elif isinstance(kwargs["type"], TransactionType):
                version = kwargs["type"]
            elif isinstance(kwargs["type"], int):
                version = TransactionType(kwargs["type"])
            else:
                # Using hex values or alike.
                version = TransactionType(self.conversion_manager.convert(kwargs["type"], int))

        elif "gas_price" in kwargs:
            version = TransactionType.STATIC
        else:
            version = self.default_transaction_type

        kwargs["type"] = version.value
        txn_class = transaction_types[version]

        if "required_confirmations" not in kwargs or kwargs["required_confirmations"] is None:
            # Attempt to use default required-confirmations from `ape-config.yaml`.
            required_confirmations = 0
            active_provider = self.network_manager.active_provider
            if active_provider:
                required_confirmations = active_provider.network.required_confirmations

            kwargs["required_confirmations"] = required_confirmations

        if isinstance(kwargs.get("chainId"), str):
            kwargs["chainId"] = int(kwargs["chainId"], 16)

        elif (
            "chainId" not in kwargs or kwargs["chainId"] is None
        ) and self.network_manager.active_provider is not None:
            kwargs["chainId"] = self.provider.chain_id

        if "input" in kwargs:
            kwargs["data"] = kwargs.pop("input")

        if all(field in kwargs for field in ("v", "r", "s")):
            kwargs["signature"] = TransactionSignature(
                v=kwargs["v"],
                r=bytes(kwargs["r"]),
                s=bytes(kwargs["s"]),
            )

        if "max_priority_fee_per_gas" in kwargs:
            kwargs["max_priority_fee"] = kwargs.pop("max_priority_fee_per_gas")
        if "max_fee_per_gas" in kwargs:
            kwargs["max_fee"] = kwargs.pop("max_fee_per_gas")

        kwargs["gas"] = kwargs.pop("gas_limit", kwargs.get("gas"))

        if "value" in kwargs and not isinstance(kwargs["value"], int):
            value = kwargs["value"] or 0  # Convert None to 0.
            kwargs["value"] = self.conversion_manager.convert(value, int)

        # This causes problems in pydantic for some reason.
        if "gas_price" in kwargs and kwargs["gas_price"] is None:
            del kwargs["gas_price"]

        # None is not allowed, the user likely means `b""`.
        if "data" in kwargs and kwargs["data"] is None:
            kwargs["data"] = b""

        return txn_class(**kwargs)

    def decode_logs(self, logs: List[Dict], *events: EventABI) -> Iterator["ContractLog"]:
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
            _types = [x.canonical_type for x in abi.abi.inputs]
            converted_arguments: Dict = {}

            for _type, (key, value) in zip(_types, event_arguments.items()):
                if isinstance(value, Struct):
                    struct_types = _type.lstrip("(").rstrip(")").split(",")
                    for struct_type, (struct_key, struct_val) in zip(struct_types, value.items()):
                        if struct_type == "address":
                            value[struct_key] = self.decode_address(struct_val)
                        elif "bytes" in struct_type:
                            value[struct_key] = HexBytes(struct_val)
                        else:
                            value[struct_key] = struct_val

                    converted_arguments[key] = value

                elif _type == "address":
                    converted_arguments[key] = self.decode_address(value)

                elif is_array(_type):
                    sub_type = "[".join(_type.split("[")[:-1])
                    if sub_type == "address":
                        converted_arguments[key] = [self.decode_address(v) for v in value]
                    else:
                        converted_arguments[key] = value

                else:
                    # No change.
                    converted_arguments[key] = value

            yield ContractLog(
                block_hash=log["blockHash"],
                block_number=log["blockNumber"],
                contract_address=self.decode_address(log["address"]),
                event_arguments=converted_arguments,
                event_name=abi.event_name,
                log_index=log["logIndex"],
                transaction_hash=log["transactionHash"],
                transaction_index=log["transactionIndex"],
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
            except ContractError:
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

    def get_python_types(self, abi_type: ABIType) -> Union[Type, Tuple, List]:
        return self._python_type_for_abi_type(abi_type)


def parse_type(type_: Dict[str, Any]) -> Union[str, Tuple, List]:
    if "tuple" not in type_["type"]:
        return type_["type"]

    result = tuple([parse_type(c) for c in type_["components"]])
    return [result] if is_array(type_["type"]) else result
