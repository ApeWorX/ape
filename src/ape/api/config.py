from enum import Enum
from typing import Any

from pydantic import BaseModel, BaseSettings


class ConfigEnum(str, Enum):
    """
    A configuration `Enum <https://docs.python.org/3/library/enum.html>`__ type.
    Use this to limit the values of a config item, such as colors ``"RED"``, ``"BLUE"``,
    ``"GREEN"``, rather than any arbitrary ``str``.
    """


class ConfigDict(BaseModel):
    __root__: dict = {}


class PluginConfig(BaseSettings):
    """
    A base plugin configuration class. Each plugin that includes
    a config API must register a subclass of this class.
    """

    def __getitem__(self, attr_name: str) -> Any:
        # allow hyphens in plugin config files
        attr_name = attr_name.replace("-", "_")

        if not hasattr(self, attr_name):
            raise AttributeError(f"{self.__class__.__name__} has no attr '{attr_name}'")

        return getattr(self, attr_name)


class GenericConfig(PluginConfig):
    """
    The default class used when no specialized class is used.
    """

    __root__: dict = {}
