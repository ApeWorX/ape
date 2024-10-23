from collections.abc import Iterable, Iterator, Sequence
from functools import cached_property
from typing import TYPE_CHECKING, Any, Optional, Union, cast

from eth_abi.abi import encode
from eth_abi.packed import encode_packed
from eth_pydantic_types import HexBytes
from eth_typing import Hash32, HexStr
from eth_utils import encode_hex, keccak, to_hex
from ethpm_types.abi import EventABI
from pydantic import BaseModel, field_serializer, field_validator, model_validator
from web3.types import FilterParams

from ape.types.address import AddressType
from ape.types.basic import HexInt
from ape.utils.basemodel import BaseInterfaceModel, ExtraAttributesMixin, ExtraModelAttributes
from ape.utils.misc import ZERO_ADDRESS, log_instead_of_fail

if TYPE_CHECKING:
    from ape.api.providers import BlockAPI
    from ape.contracts import ContractEvent


TopicFilter = Sequence[Union[Optional[HexStr], Sequence[Optional[HexStr]]]]


class LogFilter(BaseModel):
    addresses: list[AddressType] = []
    events: list[EventABI] = []
    topic_filter: TopicFilter = []
    start_block: int = 0
    stop_block: Optional[int] = None  # Use block height
    selectors: dict[str, EventABI] = {}

    @model_validator(mode="before")
    @classmethod
    def compute_selectors(cls, values):
        values["selectors"] = {
            encode_hex(keccak(text=event.selector)): event for event in values.get("events", [])
        }

        return values

    @field_validator("start_block", mode="before")
    @classmethod
    def validate_start_block(cls, value):
        return value or 0

    def model_dump(self, *args, **kwargs):
        _Hash32 = Union[Hash32, HexBytes, HexStr]
        topics = cast(Sequence[Optional[Union[_Hash32, Sequence[_Hash32]]]], self.topic_filter)
        return FilterParams(
            address=self.addresses,
            fromBlock=to_hex(self.start_block),
            toBlock=to_hex(self.stop_block or self.start_block),
            topics=topics,
        )

    @classmethod
    def from_event(
        cls,
        event: Union[EventABI, "ContractEvent"],
        search_topics: Optional[dict[str, Any]] = None,
        addresses: Optional[list[AddressType]] = None,
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
        topic_filter: list[Optional[HexStr]] = [encode_hex(keccak(text=event_abi.selector))]
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

    event_arguments: dict[str, Any] = {}
    """The arguments to the event, including both indexed and non-indexed data."""

    def __eq__(self, other: Any) -> bool:
        if self.contract_address != other.contract_address or self.event_name != other.event_name:
            return False

        for k, v in self.event_arguments.items():
            other_v = other.event_arguments.get(k)
            if v != other_v:
                return False

        return True

    @field_serializer("event_arguments")
    def _serialize_event_arguments(self, event_arguments, info):
        """
        Because of an issue with BigInt in Pydantic,
        (https://github.com/pydantic/pydantic/issues/10152)
        we have to ensure these are regular ints.
        """
        return self._serialize_value(event_arguments, info)

    def _serialize_value(self, value: Any, info) -> Any:
        if isinstance(value, int):
            # Handle custom ints.
            return int(value)

        elif isinstance(value, HexBytes):
            return to_hex(value) if info.mode == "json" else value

        elif isinstance(value, str):
            # Avoiding str triggering iterable condition.
            return value

        elif isinstance(value, dict):
            # Also, avoid handling dict in the iterable case.
            return {k: self._serialize_value(v, info) for k, v in value.items()}

        elif isinstance(value, Iterable):
            return [self._serialize_value(v, info) for v in value]

        return value


class ContractLog(ExtraAttributesMixin, BaseContractLog):
    """
    An instance of a log from a contract.
    """

    transaction_hash: Any
    """The hash of the transaction containing this log."""

    block_number: HexInt
    """The number of the block containing the transaction that produced this log."""

    block_hash: Any
    """The hash of the block containing the transaction that produced this log."""

    log_index: HexInt
    """The index of the log on the transaction."""

    transaction_index: Optional[HexInt] = None
    """
    The index of the transaction's position when the log was created.
    Is `None` when from the pending block.
    """

    @field_serializer("transaction_hash", "block_hash")
    def _serialize_hashes(self, value, info):
        return self._serialize_value(value, info)

    # NOTE: This class has an overridden `__getattr__` method, but `block` is a reserved keyword
    #       in most smart contract languages, so it is safe to use. Purposely avoid adding
    #       `.datetime` and `.timestamp` in case they are used as event arg names.
    @cached_property
    def block(self) -> "BlockAPI":
        return self.chain_manager.blocks[self.block_number]

    @property
    def timestamp(self) -> int:
        """
        The UNIX timestamp of when the event was emitted.

        NOTE: This performs a block lookup.
        """
        return self.block.timestamp

    @property
    def _event_args_str(self) -> str:
        return " ".join(f"{key}={val}" for key, val in self.event_arguments.items())

    def __str__(self) -> str:
        return f"{self.event_name}({self._event_args_str})"

    @log_instead_of_fail(default="<ContractLog>")
    def __repr__(self) -> str:
        event_arg_str = self._event_args_str
        suffix = f" {event_arg_str}" if event_arg_str else ""
        return f"<{self.event_name}{suffix}>"

    def __ape_extra_attributes__(self) -> Iterator[ExtraModelAttributes]:
        yield ExtraModelAttributes(
            name=self.event_name,
            attributes=lambda: self.event_arguments or {},
            include_getattr=True,
            include_getitem=True,
        )

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

    def get(self, item: str, default: Optional[Any] = None) -> Any:
        return self.event_arguments.get(item, default)


def _equal_event_inputs(mock_input: Any, real_input: Any) -> bool:
    if mock_input is None:
        # Check is skipped.
        return True

    elif isinstance(mock_input, (list, tuple)):
        if not isinstance(real_input, (list, tuple)) or len(real_input) != len(mock_input):
            return False

        return all(_equal_event_inputs(m, r) for m, r in zip(mock_input, real_input))

    else:
        return mock_input == real_input


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
            other_input = other.event_arguments.get(name)
            if not _equal_event_inputs(value, other_input):
                # Only exit on False; Else, keep checking.
                return False

        return True


class ContractLogContainer(list):
    """
    Container for ContractLogs which is adding capability of filtering logs
    """

    def filter(self, event: "ContractEvent", **kwargs) -> list[ContractLog]:
        return [
            x
            for x in self
            if x.event_name == event.name
            and x.contract_address == event.contract
            and all(v == x.event_arguments.get(k) and v is not None for k, v in kwargs.items())
        ]

    def __contains__(self, val: Any) -> bool:
        return any(log == val for log in self)
