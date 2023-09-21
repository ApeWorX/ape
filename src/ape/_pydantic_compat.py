# support both pydantic v1 and v2
try:
    from pydantic.v1 import (
        BaseModel,
        BaseSettings,
        Extra,
        Field,
        FileUrl,
        HttpUrl,
        NonNegativeInt,
        PositiveInt,
        ValidationError,
        root_validator,
        validator,
    )
    from pydantic.v1.dataclasses import dataclass
except ImportError:
    from pydantic import (
        BaseModel,
        Extra,
        Field,
        FileUrl,
        HttpUrl,
        NonNegativeInt,
        PositiveInt,
        ValidationError,
        root_validator,
        validator,
    )
    from pydantic.dataclasses import dataclass
    from pydantic_settings import BaseSettings

__all__ = (
    "BaseModel",
    "BaseSettings",
    "Extra",
    "Field",
    "FileUrl",
    "HttpUrl",
    "NonNegativeInt",
    "PositiveInt",
    "ValidationError",
    "root_validator",
    "validator",
    "dataclass",
)
