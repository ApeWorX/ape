from typing import Annotated, Any, Optional, Union

from eth_pydantic_types import Address as _Address
from eth_pydantic_types import HashBytes20, HashStr20
from eth_typing import ChecksumAddress
from pydantic_core.core_schema import ValidationInfo

from ape.utils.basemodel import ManagerAccessMixin

RawAddress = Union[str, int, HashStr20, HashBytes20]
"""
A raw data-type representation of an address.
"""


class _AddressValidator(_Address, ManagerAccessMixin):
    """
    An address in Ape. This types works the same as
    ``eth_pydantic_types.address.Address`` for most cases,
    (validated size and checksumming), unless your ecosystem
    has a different address type, either in bytes-length or
    checksumming algorithm.
    """

    @classmethod
    def __eth_pydantic_validate__(cls, value: Any, info: Optional[ValidationInfo] = None) -> str:
        if type(value) in (list, tuple):
            return cls.conversion_manager.convert(value, list[AddressType])

        return (
            cls.conversion_manager.convert(value, AddressType)
            if value
            else "0x0000000000000000000000000000000000000000"
        )


AddressType = Annotated[ChecksumAddress, _AddressValidator]
"""
"A checksum address in Ape."
"""


__all__ = [
    "AddressType",
    "RawAddress",
]
