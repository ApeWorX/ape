from enum import Enum
from typing import Any

from pydantic import BaseModel, BaseSettings


class ConfigEnum(str, Enum):
    pass


class ConfigDict(BaseModel):
    __root__: dict = {}


class PluginConfig(BaseSettings):
    """
    Each plugin's config must inherit from this base class
    """

    def __getitem__(self, attr_name: str) -> Any:
        if not hasattr(self, attr_name):
            raise AttributeError(f"{self.__class__.__name__} has no attr '{attr_name}'")

        return getattr(self, attr_name)


class UnprocessedConfig(PluginConfig):
    """
    The default class used when no specialized class is used
    """

    __root__: dict = {}
