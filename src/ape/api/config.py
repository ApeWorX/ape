from enum import Enum
from typing import TYPE_CHECKING, Any, Dict, Optional, TypeVar

from pydantic import ConfigDict
from pydantic_settings import BaseSettings

from ape.utils.basemodel import _assert_not_ipython_check, only_raise_attribute_error

if TYPE_CHECKING:
    from ape.managers.config import ConfigManager

ConfigItemType = TypeVar("ConfigItemType")


class ConfigEnum(str, Enum):
    """
    A configuration `Enum <https://docs.python.org/3/library/enum.html>`__ type.
    Use this to limit the values of a config item, such as colors ``"RED"``, ``"BLUE"``,
    ``"GREEN"``, rather than any arbitrary ``str``.

    Usage example::

            class MyEnum(ConfigEnum):
                FOO = "FOO"
                BAR = "BAR"

            class MyConfig(PluginConfig):
                my_enum: MyEnum

            model = MyConfig(my_enum="FOO")

    """


class PluginConfig(BaseSettings):
    """
    A base plugin configuration class. Each plugin that includes
    a config API must register a subclass of this class.
    """

    # NOTE: This is probably partially initialized at the time of assignment
    _config_manager: Optional["ConfigManager"]

    @classmethod
    def from_overrides(
        cls, overrides: Dict, config_manager: Optional["ConfigManager"] = None
    ) -> "PluginConfig":
        cls._config_manager = config_manager
        default_values = cls().model_dump()

        def update(root: Dict, value_map: Dict):
            for key, val in value_map.items():
                if isinstance(val, dict) and key in root and isinstance(root[key], dict):
                    root[key] = update(root[key], val)
                else:
                    root[key] = val

            return root

        return cls(**update(default_values, overrides))

    @only_raise_attribute_error
    def __getattr__(self, attr_name: str) -> Any:
        _assert_not_ipython_check(attr_name)

        # Allow hyphens in plugin config files.
        attr_name = attr_name.replace("-", "_")
        extra = self.__pydantic_extra__ or {}
        if attr_name in extra:
            return extra[attr_name]

        return super().__getattribute__(attr_name)

    def __getitem__(self, item: str) -> Any:
        extra = self.__pydantic_extra__ or {}
        if item in self.__dict__:
            return self.__dict__[item]

        elif item in extra:
            return extra[item]

        raise KeyError(f"'{item}' not in config.")

    def __contains__(self, key: str) -> bool:
        return key in self.__dict__ or key in (self.__pydantic_extra__ or {})

    def get(self, key: str, default: Optional[ConfigItemType] = None) -> ConfigItemType:
        extra: Dict = self.__pydantic_extra__ or {}
        return self.__dict__.get(key, extra.get(key, default))


class GenericConfig(ConfigDict):
    """
    The default class used when no specialized class is used.
    """
