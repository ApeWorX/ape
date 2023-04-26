from typing import Union

from eth_typing import ChecksumAddress as AddressType
from ethpm_types import HexBytes

RawAddress = Union[str, int, HexBytes]
"""
A raw data-type representation of an address.
"""

__all__ = [
    "AddressType",
    "RawAddress",
]
