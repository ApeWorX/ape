import sys
from typing import Union

from eth_typing import ChecksumAddress
from hexbytes import HexBytes

from .contract import ABI, Bytecode, Checksum, Compiler, ContractType, Source
from .manifest import PackageManifest, PackageMeta
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

AddressType = ChecksumAddress
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
    "Source",
    "TransactionSignature",
]
