from typing import Literal, Union

from pydantic import BaseModel, field_validator


class AutoGasLimit(BaseModel):
    """
    Additional settings for ``gas_limit: auto``.
    """

    multiplier: float = 1.0
    """
    A multiplier to estimated gas.
    """

    @field_validator("multiplier", mode="before")
    @classmethod
    def validate_multiplier(cls, value):
        if isinstance(value, str):
            return float(value)

        return value


GasLimit = Union[Literal["auto", "max"], int, str, AutoGasLimit]
"""
A value you can give to Ape for handling gas-limit calculations.
``"auto"`` refers to automatically figuring out the gas,
``"max"`` refers to using the maximum block gas limit,
and otherwise you can provide a numeric value.
"""
