from enum import Enum
from typing import Any, Dict, Union

from .base import dataclass


class ConfigEnum(str, Enum):
    pass


@dataclass(slots=True, kwargs=True)
class ConfigItem:
    """
    Each plugin must inherit from this Config base class
    """

    def serialize(self) -> Dict:
        data: Dict[str, Union[str, int, Dict]] = dict()
        for name in self.__slots__:
            value = getattr(self, name)
            if isinstance(value, ConfigItem):
                data[name] = value.serialize()
            elif isinstance(value, ConfigEnum):
                data[name] = value.name
            elif isinstance(value, (int, str, dict)):
                data[name] = value
            else:
                raise TypeError("Received unknown type when serializing a config item")
        return data

    def validate_config(self):
        pass

    def __getitem__(self, attrname: str) -> Any:
        if attrname in self.__slots__:
            return getattr(self, attrname)

        raise KeyError(f"''{attrname}'")


class ConfigDict(ConfigItem):
    def __post_init__(self):
        raise ValueError("Do not use this class directly!")
