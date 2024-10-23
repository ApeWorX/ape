from typing import Any, Optional

from pydantic_core.core_schema import (
    CoreSchema,
    ValidationInfo,
    int_schema,
    no_info_plain_validator_function,
    plain_serializer_function_ser_schema,
)
from typing_extensions import TypeAlias

from ape.exceptions import ConversionError
from ape.utils.basemodel import ManagerAccessMixin


class CurrencyValueComparable(int):
    """
    An integer you can compare with currency-value
    strings, such as ``"1 ether"``.
    """

    def __eq__(self, other: Any) -> bool:
        if isinstance(other, int):
            return super().__eq__(other)

        elif isinstance(other, str):
            try:
                other_value = ManagerAccessMixin.conversion_manager.convert(other, int)
            except ConversionError:
                # Not a currency-value, it's ok.
                return False

            return super().__eq__(other_value)

        # Try from the other end, if hasn't already.
        return NotImplemented

    def __hash__(self) -> int:
        return hash(int(self))

    @classmethod
    def __get_pydantic_core_schema__(cls, value, handler=None) -> CoreSchema:
        return no_info_plain_validator_function(
            cls._validate,
            serialization=plain_serializer_function_ser_schema(
                cls._serialize,
                info_arg=False,
                return_schema=int_schema(),
            ),
        )

    @staticmethod
    def _validate(value: Any, info: Optional[ValidationInfo] = None) -> "CurrencyValueComparable":
        # NOTE: For some reason, for this to work, it has to happen
        #   in an "after" validator, or else it always only `int` type on the model.
        if value is None:
            # Will fail if not optional.
            # Type ignore because this is an hacky and unlikely situation.
            return None  # type: ignore

        elif isinstance(value, str) and " " in value:
            return ManagerAccessMixin.conversion_manager.convert(value, int)

        # For models annotating with this type, we validate all integers into it.
        return CurrencyValueComparable(value)

    @staticmethod
    def _serialize(value):
        return int(value)


CurrencyValueComparable.__name__ = int.__name__


CurrencyValue: TypeAlias = CurrencyValueComparable
"""
An alias to :class:`~ape.types.CurrencyValueComparable` for
situations when you know for sure the type is a currency-value
(and not just comparable to one).
"""
