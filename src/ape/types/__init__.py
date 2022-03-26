from typing import Any, Dict, Union

from eth_typing import ChecksumAddress as AddressType
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
from hexbytes import HexBytes
from pydantic.dataclasses import dataclass

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


@dataclass
class ContractLog:
    """
    An instance of a log from a contract.
    """

    name: str
    """The name of the event."""

    event_arguments: Dict[str, Any]
    """The arguments to the event, including both indexed and non-indexed data."""

    transaction_hash: Any
    """The hash of the transaction containing this log."""

    block_number: int
    """The number of the block containing the transaction that produced this log."""

    block_hash: Any
    """The hash of the block containing the transaction that produced this log."""

    index: int
    """The index of the log on the transaction."""

    def __repr__(self) -> str:
        return f"<{self.name}>"

    def __getattr__(self, item: str) -> Any:
        """
        Access properties from the log via ``.`` access.

        Args:
            item (str): The name of the property.
        """

        if item not in self.event_arguments:
            raise AttributeError(f"{self.__class__.__name__} has no attribute '{item}'.")

        return self.event_arguments[item]


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
