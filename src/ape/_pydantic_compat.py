# support both pydantic v1 and v2
try:
    from pydantic.v1 import (  # type: ignore
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
except ImportError:
    from pydantic import (  # type: ignore
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
    from pydantic.dataclasses import dataclass  # type: ignore
    from pydantic_settings import BaseSettings  # type: ignore

__all__ = (
    "BaseModel",
    "BaseSettings",
    "dataclass",
    "Extra",
    "Field",
    "FileUrl",
    "HttpUrl",
    "NonNegativeInt",
    "PositiveInt",
    "ValidationError",
    "root_validator",
    "validator",
)
