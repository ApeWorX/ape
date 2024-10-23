from abc import abstractmethod
from functools import cached_property
from typing import TYPE_CHECKING, Any

from eth_pydantic_types import HexBytes

from ape.exceptions import ConversionError
from ape.types.address import AddressType
from ape.types.units import CurrencyValue
from ape.types.vm import ContractCode
from ape.utils.basemodel import BaseInterface
from ape.utils.misc import log_instead_of_fail

if TYPE_CHECKING:
    from ape.api.transactions import ReceiptAPI, TransactionAPI
    from ape.managers.chain import AccountHistory


class BaseAddress(BaseInterface):
    """
    A base address API class. All account-types subclass this type.
    """

    @property
    def _base_dir_values(self) -> list[str]:
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
            "provider",  # Is a class property
        ]

    @property
    @abstractmethod
    def address(self) -> AddressType:
        """
        The address of this account. Subclasses must override and provide this value.
        """

    def __eq__(self, other: object) -> bool:
        """
        Compares :class:`~ape.api.BaseAddress` or ``str`` objects by converting to
        :class:`~ape.types.address.AddressType`.

        Returns:
            bool: comparison result
        """

        convert = self.conversion_manager.convert

        try:
            return convert(self, AddressType) == convert(other, AddressType)
        except ConversionError:
            # Check other __eq__
            return NotImplemented

    def __dir__(self) -> list[str]:
        """
        Display methods to IPython on ``a.[TAB]`` tab completion.
        Overridden to lessen amount of methods shown to only those that are useful.

        Returns:
            list[str]: Method names that IPython uses for tab completion.
        """
        return self._base_dir_values

    @log_instead_of_fail(default="<BaseAddress>")
    def __repr__(self) -> str:
        cls_name = getattr(type(self), "__name__", BaseAddress.__name__)
        return f"<{cls_name} {self.address}>"

    def __str__(self) -> str:
        """
        Convert this class to a ``str`` address.

        Returns:
            str: The stringified address.
        """
        return self.address

    def __call__(self, **kwargs) -> "ReceiptAPI":
        """
        Call this address directly. For contracts, this may mean invoking their
        default handler.

        Args:
            **kwargs: Transaction arguments, such as ``sender`` or ``data``.

        Returns:
            :class:`~ape.api.transactions.ReceiptAPI`
        """

        txn = self.as_transaction(**kwargs)
        if "sender" in kwargs and hasattr(kwargs["sender"], "call"):
            sender = kwargs["sender"]
            return sender.call(txn, **kwargs)
        elif "sender" not in kwargs and self.account_manager.default_sender is not None:
            return self.account_manager.default_sender.call(txn, **kwargs)

        return self.provider.send_transaction(txn)

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
        bal = self.provider.get_balance(self.address)
        # By using CurrencyValue, we can compare with
        # strings like "1 ether".
        return CurrencyValue(bal)

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

    @cached_property
    def history(self) -> "AccountHistory":
        """
        The list of transactions that this account has made on the current chain.
        """
        return self.chain_manager.history[self.address]

    def as_transaction(self, **kwargs) -> "TransactionAPI":
        converted_kwargs = self.conversion_manager.convert_method_kwargs(kwargs)
        return self.provider.network.ecosystem.create_transaction(
            receiver=self.address, **converted_kwargs
        )

    def estimate_gas_cost(self, **kwargs) -> int:
        txn = self.as_transaction(**kwargs)
        return self.provider.estimate_gas_cost(txn)


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
            :class:`~ape.types.address.AddressType`: An alias to
            `ChecksumAddress <https://eth-typing.readthedocs.io/en/latest/types.html#checksumaddress>`__.  # noqa: E501
        """

        return self._address
