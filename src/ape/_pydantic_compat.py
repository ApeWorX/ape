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
    from pydantic.v1.dataclasses import dataclass  # type: ignore
except ImportError:
    from pydantic import (  # type: ignore
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
    from pydantic.dataclasses import dataclass  # type: ignore

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
