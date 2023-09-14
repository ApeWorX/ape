from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Dict, List, Literal, Optional, Union

from eth_abi.abi import encode
from eth_abi.packed import encode_packed
from eth_typing import HexStr
from eth_utils import encode_hex, keccak
from ethpm_types import (
    ABI,
    Bytecode,
    Checksum,
    Compiler,
    ContractType,
    HexBytes,
    PackageManifest,
    PackageMeta,
    Source,
)
from ethpm_types.abi import EventABI
from ethpm_types.source import Closure
from pydantic import BaseModel, root_validator, validator
from web3.types import FilterParams

from ape.exceptions import ApeAttributeError
from ape.types.address import AddressType, RawAddress
from ape.types.coverage import (
    ContractCoverage,
    ContractSourceCoverage,
    CoverageProject,
    CoverageReport,
    CoverageStatement,
)
from ape.types.signatures import MessageSignature, SignableMessage, TransactionSignature
from ape.types.trace import CallTreeNode, ControlFlow, GasReport, SourceTraceback, TraceFrame
from ape.utils import BaseInterfaceModel, cached_property
from ape.utils.misc import ZERO_ADDRESS, to_int

if TYPE_CHECKING:
    from ape.api.providers import BlockAPI
    from ape.contracts import ContractEvent

BlockID = Union[int, HexStr, HexBytes, Literal["earliest", "latest", "pending"]]
"""
An ID that can match a block, such as the literals ``"earliest"``, ``"latest"``, or ``"pending"``
as well as a block number or hash (HexBytes).
"""

ContractCode = Union[str, bytes, HexBytes]
"""
A type that represents contract code, which can be represented in string, bytes, or HexBytes.
"""

SnapshotID = Union[str, int, bytes]
"""
An ID representing a point in time on a blockchain, as used in the
:meth:`~ape.managers.chain.ChainManager.snapshot` and
:meth:`~ape.managers.chain.ChainManager.snapshot` methods. Can be a ``str``, ``int``, or ``bytes``.
Providers will expect and handle snapshot IDs differently. There shouldn't be a need to change
providers when using this feature, so there should not be confusion over this type in practical use
cases.
"""


class AutoGasLimit(BaseModel):
    """
    Additional settings for ``gas_limit: auto``.
    """

    multiplier: float = 1.0
    """
    A multiplier to estimated gas.
    """

    @validator("multiplier", pre=True)
    def validate_multiplier(cls, value):
        if isinstance(value, str):
            return float(value)

        return value


GasLimit = Union[Literal["auto", "max"], int, str, AutoGasLimit]
"""
A value you can give to Ape for handling gas-limit calculations.
``"auto"`` refers to automatically figuring out the gas,
``"max"`` refers to using the maximum block gas limit,
and otherwise you can provide a numeric value.
"""


TopicFilter = List[Union[Optional[HexStr], List[Optional[HexStr]]]]


@dataclass
class ContractFunctionPath:
    """
    Useful for identifying a method in a contract.
    """

    contract_name: str
    method_name: Optional[str] = None

    @classmethod
    def from_str(cls, value: str) -> "ContractFunctionPath":
        if ":" in value:
            contract_name, method_name = value.split(":")
            return cls(contract_name=contract_name, method_name=method_name)

        return cls(contract_name=value)

    def __str__(self) -> str:
        return f"{self.contract_name}:{self.method_name}"

    def __repr__(self) -> str:
        return f"<{self}>"


class LogFilter(BaseModel):
    addresses: List[AddressType] = []
    events: List[EventABI] = []
    topic_filter: TopicFilter = []
    start_block: int = 0
    stop_block: Optional[int] = None  # Use block height
    selectors: Dict[str, EventABI] = {}

    @root_validator()
    def compute_selectors(cls, values):
        values["selectors"] = {
            encode_hex(keccak(text=event.selector)): event for event in values.get("events", [])
        }

        return values

    @validator("start_block", pre=True)
    def validate_start_block(cls, value):
        return value or 0

    @validator("addresses", pre=True, each_item=True)
    def validate_addresses(cls, value):
        from ape import convert

        return convert(value, AddressType)

    def dict(self, client=None):
        return FilterParams(
            address=self.addresses,
            fromBlock=hex(self.start_block),  # type: ignore
            toBlock=hex(self.stop_block),  # type: ignore
            topics=self.topic_filter,  # type: ignore
        )

    @classmethod
    def from_event(
        cls,
        event: Union[EventABI, "ContractEvent"],
        search_topics: Optional[Dict[str, Any]] = None,
        addresses: Optional[List[AddressType]] = None,
        start_block=None,
        stop_block=None,
    ):
        """
        Construct a log filter from an event topic query.
        """
        from ape import convert
        from ape.utils.abi import LogInputABICollection, is_dynamic_sized_type

        event_abi: EventABI = getattr(event, "abi", event)  # type: ignore
        search_topics = search_topics or {}
        topic_filter: List[Optional[HexStr]] = [encode_hex(keccak(text=event_abi.selector))]
        abi_inputs = LogInputABICollection(event_abi)

        def encode_topic_value(abi_type, value):
            if isinstance(value, (list, tuple)):
                return [encode_topic_value(abi_type, v) for v in value]
            elif is_dynamic_sized_type(abi_type):
                return encode_hex(keccak(encode_packed([str(abi_type)], [value])))
            elif abi_type == "address":
                value = convert(value, AddressType)

            return encode_hex(encode([abi_type], [value]))

        for topic in abi_inputs.topic_abi_types:
            if topic.name in search_topics:
                encoded_value = encode_topic_value(topic.type, search_topics[topic.name])
                topic_filter.append(encoded_value)
            else:
                topic_filter.append(None)

        topic_names = [i.name for i in abi_inputs.topic_abi_types if i.name]
        invalid_topics = set(search_topics) - set(topic_names)
        if invalid_topics:
            raise ValueError(
                f"{event_abi.name} defines {', '.join(topic_names)} as indexed topics, "
                f"but you provided {', '.join(invalid_topics)}"
            )

        # remove trailing wildcards since they have no effect
        while topic_filter[-1] is None:
            topic_filter.pop()

        return cls(
            addresses=addresses or [],
            events=[event_abi],
            topic_filter=topic_filter,
            start_block=start_block,
            stop_block=stop_block,
        )


class BaseContractLog(BaseInterfaceModel):
    """
    Base class representing information relevant to an event instance.
    """

    event_name: str
    """The name of the event."""

    contract_address: AddressType = ZERO_ADDRESS
    """The contract responsible for emitting the log."""

    event_arguments: Dict[str, Any] = {}
    """The arguments to the event, including both indexed and non-indexed data."""

    @validator("contract_address", pre=True)
    def validate_address(cls, value):
        return cls.conversion_manager.convert(value, AddressType)

    def __eq__(self, other: Any) -> bool:
        if self.contract_address != other.contract_address or self.event_name != other.event_name:
            return False

        for k, v in self.event_arguments.items():
            other_v = other.event_arguments.get(k)
            if v != other_v:
                return False

        return True


class ContractLog(BaseContractLog):
    """
    An instance of a log from a contract.
    """

    transaction_hash: Any
    """The hash of the transaction containing this log."""

    block_number: int
    """The number of the block containing the transaction that produced this log."""

    block_hash: Any
    """The hash of the block containing the transaction that produced this log."""

    log_index: int
    """The index of the log on the transaction."""

    transaction_index: Optional[int] = None
    """
    The index of the transaction's position when the log was created.
    Is `None` when from the pending block.
    """

    @validator("block_number", "log_index", "transaction_index", pre=True)
    def validate_hex_ints(cls, value):
        if value is None:
            # Should only happen for optionals.
            return value

        elif not isinstance(value, int):
            return to_int(value)

        return value

    @validator("contract_address", pre=True)
    def validate_address(cls, value):
        return cls.conversion_manager.convert(value, AddressType)

    # NOTE: This class has an overridden `__getattr__` method, but `block` is a reserved keyword
    #       in most smart contract languages, so it is safe to use. Purposely avoid adding
    #       `.datetime` and `.timestamp` in case they are used as event arg names.
    @cached_property
    def block(self) -> "BlockAPI":
        return self.chain_manager.blocks[self.block_number]

    @property
    def _event_args_str(self) -> str:
        return " ".join(f"{key}={val}" for key, val in self.event_arguments.items())

    def __str__(self) -> str:
        return f"{self.event_name}({self._event_args_str})"

    def __repr__(self) -> str:
        return f"<{self.event_name} {self._event_args_str}>"

    def __getattr__(self, item: str) -> Any:
        """
        Access properties from the log via ``.`` access.

        Args:
            item (str): The name of the property.
        """

        try:
            return self.__getattribute__(item)
        except AttributeError:
            pass

        if item not in self.event_arguments:
            raise ApeAttributeError(f"{self.__class__.__name__} has no attribute '{item}'.")

        return self.event_arguments[item]

    def __contains__(self, item: str) -> bool:
        return item in self.event_arguments

    def __eq__(self, other: Any) -> bool:
        """
        Check for equality between this instance and another ContractLog instance.

        If the other object is not an instance of ContractLog, this method returns
        NotImplemented. This triggers the Python interpreter to call the __eq__ method
        on the other object (i.e., y.__eq__(x)) if it is defined, allowing for a custom
        comparison. This behavior is leveraged by the MockContractLog class to handle
        custom comparison logic between ContractLog and MockContractLog instances.

        Args:
            other (Any): The object to compare with this instance.

        Returns:
            bool: True if the two instances are equal, False otherwise.
        """

        if not isinstance(other, ContractLog):
            return NotImplemented

        # call __eq__ on parent class
        return super().__eq__(other)

    def __getitem__(self, item: str) -> Any:
        return self.event_arguments[item]

    def get(self, item: str, default: Optional[Any] = None) -> Any:
        return self.event_arguments.get(item, default)


class MockContractLog(BaseContractLog):
    """
    A mock version of the ContractLog class used for testing purposes.
    This class is designed to match a subset of event arguments in a ContractLog instance
    by only comparing those event arguments that the user explicitly provides.

    Inherits from :class:`~ape.types.BaseContractLog`, and overrides the
    equality method for custom comparison
    of event arguments between a MockContractLog and a ContractLog instance.
    """

    def __eq__(self, other: Any) -> bool:
        if (
            not hasattr(other, "contract_address")
            or not hasattr(other, "event_name")
            or self.contract_address != other.contract_address
            or self.event_name != other.event_name
        ):
            return False

        # NOTE: `self.event_arguments` contains a subset of items from `other.event_arguments`,
        #       but we skip those the user doesn't care to check
        for name, value in self.event_arguments.items():
            # Make sure `value` is not `None` (user explicitly set it `None`)
            # NOTE: `other.event_arguments[name]` will raise `IndexError` only if ABIs don't match
            if value is not None and value != other.event_arguments[name]:
                return False

        return True


class ContractLogContainer(list):
    """
    Container for ContractLogs which is adding capability of filtering logs
    """

    def filter(self, event: "ContractEvent", **kwargs) -> List[ContractLog]:
        return [
            x
            for x in self
            if x.event_name == event.name
            and x.contract_address == event.contract
            and all(v == x.event_arguments.get(k) and v is not None for k, v in kwargs.items())
        ]

    def __contains__(self, val: Any) -> bool:
        return any(log == val for log in self)


__all__ = [
    "ABI",
    "AddressType",
    "BlockID",
    "Bytecode",
    "CallTreeNode",
    "Checksum",
    "Closure",
    "Compiler",
    "ContractCoverage",
    "ContractSourceCoverage",
    "ContractLog",
    "ContractLogContainer",
    "ContractType",
    "ControlFlow",
    "CoverageItem",
    "CoverageProject",
    "CoverageReport",
    "CoverageStatement",
    "GasReport",
    "MessageSignature",
    "PackageManifest",
    "PackageMeta",
    "RawAddress",
    "SignableMessage",
    "SnapshotID",
    "Source",
    "SourceTraceback",
    "TraceFrame",
    "TransactionSignature",
]
