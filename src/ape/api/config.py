from enum import Enum
from typing import Any, Dict, Optional

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

    @classmethod
    def from_overrides(cls, overrides: Dict) -> "PluginConfig":
        default_values = cls().dict()

        def update(root: Dict, value_map: Dict):
            for key, val in value_map.items():
                if key in root and isinstance(val, dict):
                    root[key] = update(root[key], val)
                else:
                    root[key] = val

            return root

        return cls(**update(default_values, overrides))

    def __getattr__(self, attr_name: str) -> Any:
        # allow hyphens in plugin config files
        attr_name = attr_name.replace("-", "_")
        return super().__getattribute__(attr_name)

    def __getitem__(self, item: str) -> Any:
        return self.__dict__[item]

    def __contains__(self, key: str) -> bool:
        return key in self.__dict__

    def get(self, key: str, default: Optional[Any] = None) -> Any:
        return self.__dict__.get(key, default)


class GenericConfig(PluginConfig):
    """
    The default class used when no specialized class is used.
    """

    __root__: dict = {}
