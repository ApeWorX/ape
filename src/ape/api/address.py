from typing import List

from ape.api.providers import ProviderAPI
from ape.exceptions import AddressError
from ape.types import AddressType
from ape.utils import BaseInterface, abstractmethod


class AddressBase(BaseInterface):
    """
    A base address API class. All account-types subclass this type.
    """

    @property
    def provider(self) -> ProviderAPI:
        """
        The current active provider if connected to one.

        Raises:
            :class:`~ape.exceptions.AddressError`: When there is no active
               provider at runtime.

        Returns:
            :class:`~ape.api.providers.ProviderAPI`
        """
        if self.network_manager.active_provider is None:
            raise AddressError(
                f"Incorrectly implemented provider API for class '{type(self).__name__}'."
            )

        return self.network_manager.active_provider

    @property
    @abstractmethod
    def address(self) -> AddressType:
        """
        The address of this account. Subclasses must override and provide this value.
        """

    def __eq__(self, other: object) -> bool:
        """
        Compares :class:`~ape.api.AddressBase` / ``str`` objects by converting to ``AddressType``.

        Returns:
            bool: comparison result
        """

        convert = self.conversion_manager.convert
        return convert(self, AddressType) == convert(other, AddressType)

    def __dir__(self) -> List[str]:
        """
        Display methods to IPython on ``a.[TAB]`` tab completion.

        Returns:
            List[str]: Method names that IPython uses for tab completion.
        """
        return [
            "address",
            "balance",
            "code",
            "codesize",
            "nonce",
            "is_contract",
            "provider",
        ]

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

    @property
    def code(self) -> bytes:
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

        return len(self.code) > 0


class Address(AddressBase):
    """
    A generic blockchain address.

    Typically, this is used when we do not know the contract type at a given address,
    or to refer to an EOA the user doesn't personally control.
    """

    _address: AddressType

    @property
    def address(self) -> AddressType:
        """
        The raw address type.

        Returns:
            ``AddressType``: An alias to
            `ChecksumAddress <https://eth-typing.readthedocs.io/en/latest/types.html#checksumaddress>`__.  # noqa: E501
        """

        return self._address
