import sys
from typing import Union

from eth_typing import ChecksumAddress
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

from .signatures import MessageSignature, SignableMessage, TransactionSignature

# We can remove this once we stop supporting python3.7.
if sys.version_info >= (3, 8):
    from typing import Literal
else:
    from typing_extensions import Literal


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

AddressType = ChecksumAddress  # type: ignore
"""A type representing a checksummed address."""

__all__ = [
    "ABI",
    "AddressType",
    "BlockID",
    "Bytecode",
    "Checksum",
    "Compiler",
    "ContractType",
    "MessageSignature",
    "PackageManifest",
    "PackageMeta",
    "SignableMessage",
    "SnapshotID",
    "Source",
    "TransactionSignature",
]
