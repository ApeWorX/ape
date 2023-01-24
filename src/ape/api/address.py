from typing import Any, List

from hexbytes import HexBytes

from ape.exceptions import ConversionError
from ape.types import AddressType, ContractCode
from ape.utils import BaseInterface, abstractmethod


class BaseAddress(BaseInterface):
    """
    A base address API class. All account-types subclass this type.
    """

    @property
    def _base_dir_values(self) -> List[str]:
        """
        This exists because when you call ``dir(BaseAddress)``, you get the type's return
        value and not the instances. This allows base-classes to make use of shared
        ``IPython`` ``__dir__`` values.
        """

        # NOTE: mypy is confused by properties.
        #  https://github.com/python/typing/issues/1112
        return [
            str(BaseAddress.address.fget.__name__),  # type: ignore[attr-defined]
            str(BaseAddress.balance.fget.__name__),  # type: ignore[attr-defined]
            str(BaseAddress.code.fget.__name__),  # type: ignore[attr-defined]
            str(BaseAddress.codesize.fget.__name__),  # type: ignore[attr-defined]
            str(BaseAddress.nonce.fget.__name__),  # type: ignore[attr-defined]
            str(BaseAddress.is_contract.fget.__name__),  # type: ignore[attr-defined]
            str(BaseAddress.provider.fget.__name__),  # type: ignore[attr-defined]
        ]

    @property
    @abstractmethod
    def address(self) -> AddressType:
        """
        The address of this account. Subclasses must override and provide this value.
        """

    def __eq__(self, other: object) -> bool:
        """
        Compares :class:`~ape.api.BaseAddress` / ``str`` objects by converting to ``AddressType``.

        Returns:
            bool: comparison result
        """

        convert = self.conversion_manager.convert

        try:
            return convert(self, AddressType) == convert(other, AddressType)
        except ConversionError:
            return False

    def __dir__(self) -> List[str]:
        """
        Display methods to IPython on ``a.[TAB]`` tab completion.
        Overridden to lessen amount of methods shown to only those that are useful.

        Returns:
            List[str]: Method names that IPython uses for tab completion.
        """
        return self._base_dir_values

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} {self.address}>"

    def __str__(self) -> str:
        """
        Convert this class to a ``str`` address.

        Returns:
            str: The stringified address.
        """
        return self.address

    @property
    def nonce(self) -> int:
        """
        The number of transactions associated with the address.
        """

        return self.provider.get_nonce(self.address)

    @property
    def balance(self) -> int:
        """
        The total balance of the account.
        """

        return self.provider.get_balance(self.address)

    # @balance.setter
    # NOTE: commented out because of failure noted within `__setattr__`
    def _set_balance_(self, value: Any):
        if isinstance(value, str):
            value = self.conversion_manager.convert(value, int)

        self.provider.set_balance(self.address, value)

    def __setattr__(self, attr: str, value: Any) -> None:
        # NOTE: Need to do this until https://github.com/pydantic/pydantic/pull/2625 is figured out
        if attr == "balance":
            self._set_balance_(value)

        else:
            super().__setattr__(attr, value)

    @property
    def code(self) -> ContractCode:
        """
        The raw bytes of the smart-contract code at the address.
        """

        # TODO: Explore caching this (based on `self.provider.network` and examining code)
        return self.provider.get_code(self.address)

    @property
    def codesize(self) -> int:
        """
        The number of bytes in the smart contract.
        """

        return len(self.code)

    @property
    def is_contract(self) -> bool:
        """
        ``True`` when there is code associated with the address.
        """

        return len(HexBytes(self.code)) > 0


class Address(BaseAddress):
    """
    A generic blockchain address.

    Typically, this is used when we do not know the contract type at a given address,
    or to refer to an EOA the user doesn't personally control.
    """

    def __init__(self, address: AddressType):
        self._address = address

    @property
    def address(self) -> AddressType:
        """
        The raw address type.

        Returns:
            ``AddressType``: An alias to
            `ChecksumAddress <https://eth-typing.readthedocs.io/en/latest/types.html#checksumaddress>`__.  # noqa: E501
        """

        return self._address
