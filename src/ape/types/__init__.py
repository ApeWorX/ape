import sys
from typing import Union

from eth_typing import ChecksumAddress as AddressType
from hexbytes import HexBytes

from .contract import ABI, Bytecode, Checksum, Compiler, ContractType, Source
from .manifest import PackageManifest, PackageMeta
from .signatures import MessageSignature, SignableMessage, TransactionSignature

# We can remove this once we stop supporting python3.7.
if sys.version_info >= (3, 8):
    from typing import Literal
else:
    from typing_extensions import Literal

BlockId = Union[str, int, HexBytes, Literal["latest"], Literal["pending"]]

__all__ = [
    "ABI",
    "AddressType",
    "BlockId",
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
