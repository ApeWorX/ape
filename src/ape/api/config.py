from enum import Enum
from typing import Any, Dict, List, Union

from ape.logging import logger
from ape.utils import dataclass


class ConfigEnum(str, Enum):
    pass


@dataclass(slots=True, kwargs=True)
class ConfigItem:
    """
    Each plugin must inherit from this Config base class
    """

    def serialize(self) -> Dict:
        """
        Convert to a dict.
        """
        data: Dict[str, Union[str, int, Dict, List, None]] = dict()
        for name in self.__slots__:
            value = getattr(self, name)
            if isinstance(value, ConfigItem):
                data[name] = value.serialize()
            elif isinstance(value, ConfigEnum):
                data[name] = value.name
            elif value is None or isinstance(value, (int, str, dict, list)):
                data[name] = value
            else:
                logger.error(
                    f"Received unknown type '{type(value)}' when serializing a config item."
                )
        return data

    def validate_config(self):
        pass

    def __getitem__(self, attrname: str) -> Any:
        if attrname in self.__slots__:
            return getattr(self, attrname)

        raise KeyError(f"{attrname!r}")


class ConfigDict(ConfigItem):
    """
    A config class that is generic and key-value based.
    """

    def __post_init__(self):
        raise ValueError("Do not use this class directly!")
