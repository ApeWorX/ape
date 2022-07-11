from typing import Any, Dict, List, Optional, Union

from eth_abi.abi import encode_single
from eth_abi.packed import encode_single_packed
from eth_typing import ChecksumAddress as AddressType
from eth_utils import encode_hex, keccak
from ethpm_types import (
    ABI,
    Bytecode,
    Checksum,
    Compiler,
    ContractType,
    PackageManifest,
    PackageMeta,
    Source,
)
from ethpm_types.abi import EventABI
from hexbytes import HexBytes
from pydantic import BaseModel, root_validator, validator

from ape._compat import Literal

from .signatures import MessageSignature, SignableMessage, TransactionSignature

BlockID = Union[str, int, HexBytes, Literal["earliest", "latest", "pending"]]
"""
An ID that can match a block, such as the literals ``"earliest"``, ``"latest"``, or ``"pending"``
as well as a block number or hash (HexBytes).
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

RawAddress = Union[str, int, HexBytes]
"""
A raw data-type representation of an address.
"""


class TopicFilter(BaseModel):
    event: EventABI
    search_values: Dict[str, Optional[Union[Any, List[Any]]]] = {}

    @property
    def event_signature_hash(self) -> str:
        return encode_hex(keccak(text=self.event.selector))

    @root_validator(pre=True)
    def validate_search_values(cls, values):
        from ape.utils import is_dynamic_sized_type

        values["event"] = (
            values["event"].abi if hasattr(values["event"], "abi") else values["event"]
        )
        input_types = {i.name: i.type for i in values["event"].inputs}

        def encode_topic_value(key, value):
            if hasattr(value, "address"):
                value = value.address

            abi_type = input_types.get(key)

            if not abi_type or value is None:
                return None

            elif isinstance(value, (list, tuple)):
                return [encode_topic_value(key, v) for v in value]

            elif is_dynamic_sized_type(abi_type):
                return encode_hex(keccak(encode_single_packed(str(abi_type), value)))

            else:
                return encode_hex(encode_single(abi_type, value))  # type: ignore

        search_values = {k: encode_topic_value(k, v) for k, v in values["search_values"].items()}
        return {**values, "search_values": search_values}

    def encode(self) -> List:
        from ape import convert
        from ape.utils.abi import LogInputABICollection

        encoded_filter_list: List = [self.event_signature_hash]
        topic_collection = LogInputABICollection(
            self.event,
            [abi_input for abi_input in self.event.inputs if abi_input.indexed],
            True,
        )

        for topic in topic_collection.values:
            if topic.name not in self.search_values:
                encoded_filter_list.append(None)
                continue

            value = self.search_values[topic.name]
            encoded_filter_list.append(value)

        valid_names = [item.name for item in topic_collection.values]
        if set(self.search_values) - set(valid_names):
            raise ValueError(
                f"{self.event.name} has these indexed topics {valid_names}, but you provided {sorted(self.search_values)}"
            )

        return encoded_filter_list


class LogFilter(BaseModel):
    contract_addresses: List[AddressType] = []
    topic_filters: List[TopicFilter] = []
    start_block: int = 0
    stop_block: Optional[int] = None  # Use block height

    @root_validator()
    def validate_start_and_stop(cls, values):
        start = values.get("start_block") or 0
        stop = values.get("stop_block") or 0
        if start > stop:
            raise ValueError("'start_block' cannot be greater than 'stop_block'.")

        return values

    @validator("start_block", pre=True)
    def validate_start_block(cls, value):
        return value or 0

    @validator("contract_addresses", pre=True)
    def validate_addresses(cls, value):
        from ape import convert

        return [convert(a, AddressType) for a in value]

    def __getitem__(self, topic_id: str) -> TopicFilter:
        topic = self.get(topic_id)
        if not topic:
            raise ValueError(f"Topic '{topic_id}' not found.")

        return topic

    def __contains__(self, topic_id: str) -> bool:
        return self.get(topic_id) is not None

    def get(self, topic_id: str) -> Optional[TopicFilter]:
        for topic in self.topic_filters:
            if topic.event_signature_hash == topic_id:
                return topic

        return None

    def encode_topics(self) -> List:
        topics = [t.encode() for t in self.topic_filters]
        if len(topics) == 1:
            # Not OR-ing any topics
            return topics[0]

        return topics


class ContractLog(BaseModel):
    """
    An instance of a log from a contract.
    """

    name: str
    """The name of the event."""

    contract_address: AddressType
    """The contract responsible for emitting the log."""

    event_arguments: Dict[str, Any]
    """The arguments to the event, including both indexed and non-indexed data."""

    transaction_hash: Any
    """The hash of the transaction containing this log."""

    block_number: int
    """The number of the block containing the transaction that produced this log."""

    block_hash: Any
    """The hash of the block containing the transaction that produced this log."""

    log_index: int
    """The index of the log on the transaction."""

    def __repr__(self) -> str:
        return f"<{self.name}>"

    def __getattr__(self, item: str) -> Any:
        """
        Access properties from the log via ``.`` access.

        Args:
            item (str): The name of the property.
        """

        try:
            normal_attribute = self.__getattribute__(item)
            return normal_attribute
        except AttributeError:
            pass

        if item not in self.event_arguments:
            raise AttributeError(f"{self.__class__.__name__} has no attribute '{item}'.")

        return self.event_arguments[item]

    def __contains__(self, item: str) -> bool:
        return item in self.event_arguments

    def __getitem__(self, item: str) -> Any:
        return self.event_arguments[item]

    def get(self, item: str, default: Optional[Any] = None) -> Any:
        return self.event_arguments.get(item, default)


__all__ = [
    "ABI",
    "AddressType",
    "BlockID",
    "Bytecode",
    "Checksum",
    "Compiler",
    "ContractLog",
    "ContractType",
    "MessageSignature",
    "PackageManifest",
    "PackageMeta",
    "SignableMessage",
    "SnapshotID",
    "Source",
    "TransactionSignature",
]
