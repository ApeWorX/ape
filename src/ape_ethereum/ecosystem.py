import re
from copy import deepcopy
from enum import IntEnum
from typing import Any, Dict, Iterator, List, Optional, Tuple, Type, Union, cast

from eth_abi import decode, encode
from eth_abi.exceptions import InsufficientDataBytes
from eth_typing import Hash32
from eth_utils import (
    encode_hex,
    humanize_hash,
    is_0x_prefixed,
    is_hex,
    is_hex_address,
    keccak,
    to_checksum_address,
    to_int,
)
from ethpm_types.abi import ABIType, ConstructorABI, EventABI, MethodABI
from hexbytes import HexBytes
from pydantic import Field, validator

from ape.api import BlockAPI, EcosystemAPI, PluginConfig, ReceiptAPI, TransactionAPI
from ape.api.networks import LOCAL_NETWORK_NAME, ProxyInfoAPI
from ape.contracts.base import ContractCall
from ape.exceptions import (
    ApeException,
    APINotImplementedError,
    ContractError,
    ConversionError,
    DecodingError,
)
from ape.logging import logger
from ape.types import (
    AddressType,
    CallTreeNode,
    ContractLog,
    GasLimit,
    RawAddress,
    TransactionSignature,
)
from ape.utils import (
    DEFAULT_LOCAL_TRANSACTION_ACCEPTANCE_TIMEOUT,
    DEFAULT_TRANSACTION_ACCEPTANCE_TIMEOUT,
    ZERO_ADDRESS,
    LogInputABICollection,
    Struct,
    StructParser,
    is_array,
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
    transaction_acceptance_timeout: int = DEFAULT_TRANSACTION_ACCEPTANCE_TIMEOUT
    default_transaction_type: TransactionType = TransactionType.DYNAMIC

    gas_limit: GasLimit = "auto"
    """
    The gas limit override to use for the network. If set to ``"auto"``, ape will
    estimate gas limits based on the transaction. If set to ``"max"`` the gas limit
    will be set to the maximum block gas limit for the network. Otherwise an ``int``
    can be used to specify an explicit gas limit amount (either base 10 or 16).

    The default for local networks is ``"max"``, otherwise ``"auto"``.
    """

    class Config:
        smart_union = True

    @validator("gas_limit", pre=True, allow_reuse=True)
    def validate_gas_limit(cls, value):
        if value in ("auto", "max"):
            return value

        elif isinstance(value, int):
            return value

        elif isinstance(value, str) and value.isnumeric():
            return int(value)

        elif is_hex(value) and is_0x_prefixed(value):
            return to_int(HexBytes(value))

        elif is_hex(value):
            raise ValueError("Gas limit hex str must include '0x' prefix.")

        raise ValueError(f"Invalid gas limit '{value}'")


def _create_local_config(default_provider: Optional[str] = None, **kwargs) -> NetworkConfig:
    return _create_config(
        required_confirmations=0,
        default_provider=default_provider,
        transaction_acceptance_timeout=DEFAULT_LOCAL_TRANSACTION_ACCEPTANCE_TIMEOUT,
        gas_limit="max",
        **kwargs,
    )


def _create_config(required_confirmations: int = 2, **kwargs) -> NetworkConfig:
    return NetworkConfig(required_confirmations=required_confirmations, **kwargs)


class EthereumConfig(PluginConfig):
    mainnet: NetworkConfig = _create_config(block_time=13)
    mainnet_fork: NetworkConfig = _create_local_config()
    goerli: NetworkConfig = _create_config(block_time=15)
    goerli_fork: NetworkConfig = _create_local_config()
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


class Ethereum(EcosystemAPI):
    name: str = "ethereum"

    """
    Default transaction type should be overidden id chain doesn't support EIP-1559
    """

    fee_token_symbol: str = "ETH"

    @property
    def config(self) -> EthereumConfig:
        return self.config_manager.get_config("ethereum")  # type: ignore

    @property
    def default_transaction_type(self) -> TransactionType:
        network = self.default_network.replace("-", "_")
        return self.config[network].default_transaction_type

    @classmethod
    def decode_address(cls, raw_address: RawAddress) -> AddressType:
        if isinstance(raw_address, int):
            raw_address = HexBytes(raw_address)

        return to_checksum_address(raw_address)

    @classmethod
    def encode_address(cls, address: AddressType) -> RawAddress:
        return str(address)

    def get_proxy_info(self, address: AddressType) -> Optional[ProxyInfo]:
        contract_code = self.provider.get_code(address)
        if isinstance(contract_code, bytes):
            contract_code = contract_code.hex()

        code = contract_code[2:]
        if not code:
            return None

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

        def str_to_slot(text):
            return int(keccak(text=text).hex(), 16)

        slots = {
            ProxyType.Standard: str_to_slot("eip1967.proxy.implementation") - 1,
            ProxyType.Beacon: str_to_slot("eip1967.proxy.beacon") - 1,
            ProxyType.OpenZeppelin: str_to_slot("org.zeppelinos.proxy.implementation"),
            ProxyType.UUPS: str_to_slot("PROXIABLE"),
        }
        for type, slot in slots.items():
            try:
                storage = self.provider.get_storage_at(address, slot)
            except APINotImplementedError:
                continue

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
                target = ContractCall(abi, target)(skip_trace=True)

            return ProxyInfo(type=type, target=target)

        # gnosis safe stores implementation in slot 0, read `NAME()` to be sure
        abi = MethodABI(
            type="function",
            name="NAME",
            stateMutability="view",
            outputs=[ABIType(type="string")],
        )
        try:
            name = ContractCall(abi, address)(skip_trace=True)
            raw_target = self.provider.get_storage_at(address, 0)[-20:].hex()
            target = self.conversion_manager.convert(raw_target, AddressType)
            # NOTE: `target` is set in initialized proxies
            if name in ("Gnosis Safe", "Default Callback Handler") and target != ZERO_ADDRESS:
                return ProxyInfo(type=ProxyType.GnosisSafe, target=target)

        except (ApeException):
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
            proxy_type = ContractCall(proxy_type_abi, address)(skip_trace=True)
            if proxy_type not in (1, 2):
                raise ValueError(f"ProxyType '{proxy_type}' not permitted by EIP-897.")

            target = ContractCall(implementation_abi, address)(skip_trace=True)
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

        txn_hash = data.get("hash") or data.get("txn_hash") or data.get("transaction_hash")

        if txn_hash:
            txn_hash = txn_hash.hex() if isinstance(txn_hash, HexBytes) else txn_hash

        data_bytes = data.get("data", b"")
        if data_bytes and isinstance(data_bytes, str):
            data["data"] = HexBytes(data_bytes)

        elif "input" in data and isinstance(data["input"], str):
            data["input"] = HexBytes(data["input"])

        receipt = Receipt(
            block_number=data.get("block_number") or data.get("blockNumber"),
            contract_address=data.get("contract_address") or data.get("contractAddress"),
            gas_limit=data.get("gas") or data.get("gas_limit") or data.get("gasLimit"),
            gas_price=data.get("gas_price") or data.get("gasPrice"),
            gas_used=data.get("gas_used") or data.get("gasUsed"),
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
        output_types_str = [o.canonical_type for o in abi.outputs]
        output_types = [parse_type(o.dict()) for o in abi.outputs]

        try:
            vm_return_values = decode(output_types_str, raw_data)
        except InsufficientDataBytes as err:
            raise DecodingError() from err

        if not vm_return_values:
            return vm_return_values

        elif not isinstance(vm_return_values, (tuple, list)):
            vm_return_values = (vm_return_values,)

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
        if isinstance(value, HexBytes):
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
        txn.data = self.get_method_selector(abi)
        txn.data += self.encode_calldata(abi, *args)

        return txn  # type: ignore

    def create_transaction(self, **kwargs) -> TransactionAPI:
        """
        Returns a transaction using the given constructor kwargs.

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
            elif not isinstance(kwargs["type"], int):
                version = TransactionType(self.conversion_manager.convert(kwargs["type"], int))
            else:
                version = TransactionType(kwargs["type"])

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

        elif "chainId" not in kwargs:
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
        return txn_class(**kwargs)

    def decode_logs(self, logs: List[Dict], *events: EventABI) -> Iterator["ContractLog"]:
        abi_inputs = {
            encode_hex(keccak(text=abi.selector)): LogInputABICollection(abi) for abi in events
        }

        for log in logs:
            if log.get("anonymous"):
                raise NotImplementedError(
                    "decoding anonymous logs is not supported with this method"
                )
            topics = log["topics"]
            # web3.py converts topics to hexbytes, data is always a hexstr
            if isinstance(log["topics"][0], bytes):
                topics = [encode_hex(t) for t in log["topics"]]
            try:
                abi = abi_inputs[topics[0]]
            except KeyError:
                continue

            try:
                event_arguments = abi.decode(topics, log["data"])
            except InsufficientDataBytes:
                logger.debug("failed to decode log data for %s", log, exc_info=True)
                continue

            yield ContractLog(
                block_hash=log["blockHash"],
                block_number=log["blockNumber"],
                contract_address=self.decode_address(log["address"]),
                event_arguments=event_arguments,
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

        contract_type = self.chain_manager.contracts.get(address)
        if not contract_type:
            return enriched_call

        enriched_call.contract_id = self._enrich_address(address, **kwargs)
        method_id_bytes = HexBytes(enriched_call.method_id) if enriched_call.method_id else None
        if method_id_bytes and method_id_bytes in contract_type.methods:
            method_abi = contract_type.methods[method_id_bytes]
            enriched_call.method_id = method_abi.name or enriched_call.method_id
            enriched_call = self._enrich_calldata(enriched_call, method_abi, **kwargs)
            enriched_call = self._enrich_returndata(enriched_call, method_abi, **kwargs)

        return enriched_call

    def _enrich_address(self, address: AddressType, **kwargs) -> str:
        if address and address == kwargs.get("sender"):
            return "tx.origin"

        elif address == ZERO_ADDRESS:
            return "ZERO_ADDRESS"

        contract_type = self.chain_manager.contracts.get(address)
        if not contract_type:
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

            if symbol and str(symbol).strip():
                return str(symbol).strip()

        name = contract_type.name.strip() if contract_type.name else None
        return name or self._get_contract_id_from_address(address)

    def _get_contract_id_from_address(self, address: "AddressType") -> str:
        if address in self.account_manager:
            return f"Transferring {self.fee_token_symbol}"

        return address

    def _enrich_calldata(self, call: CallTreeNode, method_abi: MethodABI, **kwargs) -> CallTreeNode:
        calldata = call.inputs
        if isinstance(calldata, str):
            calldata_arg = HexBytes(calldata)
        elif isinstance(calldata, HexBytes):
            calldata_arg = calldata
        else:
            # Not sure if we can get here.
            # Mostly for mypy's sake.
            return call

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
        default_return_value = "<?>"

        if isinstance(call.outputs, str) and is_0x_prefixed(call.outputs):
            return_value_bytes = HexBytes(call.outputs)
        elif isinstance(call.outputs, HexBytes):
            return_value_bytes = call.outputs
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
            except (DecodingError, InsufficientDataBytes):
                if return_value_bytes == HexBytes("0x"):
                    # Empty result, but it failed decoding because of its length.
                    return_values = ("",)

            values = (
                tuple([default_return_value for _ in method_abi.outputs])
                if return_values is None
                else tuple([self._enrich_value(v, **kwargs) for v in return_values or ()])
            )

        call.outputs = values[0] if len(values) == 1 else values
        return call


def parse_type(type: Dict[str, Any]) -> Union[str, Tuple, List]:
    if "tuple" not in type["type"]:
        return type["type"]

    result = tuple([parse_type(c) for c in type["components"]])
    return [result] if is_array(type["type"]) else result
