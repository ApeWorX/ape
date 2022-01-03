from enum import Enum
from typing import Any, Dict, List, Optional, Union

from ape.logging import logger
from ape.utils import dataclass


class ConfigEnum(str, Enum):
    """
    A configuration `Enum <https://docs.python.org/3/library/enum.html>`__ type.
    Use this to limit the values of a config item, such as colors ``"RED"``, ``"BLUE"``,
    ``"GREEN"``, rather than any arbitrary ``str``.
    """


@dataclass(slots=True, kwargs=True)
class ConfigItem:
    """
    A base plugin configuration class. Each plugin that includes
    a config API must register a subclass of this class.
    """

    def serialize(self) -> Dict:
        """
        Serialize the config item into a raw dict format for storing on disk.

        Returns:
            Dict
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
        """
        Get a configuration setting property by name. Use
        :meth:`~ape.api.config.ConfigItem.get` when it is ok for the key not to
        exist in the config.

        Raises:
            KeyError: When the attribute name is not a key in the config.

        Args:
            attrname (str): The configuration setting key.

        Returns:
            Any: The value from the config.
        """

        if attrname in self.__slots__:
            return getattr(self, attrname)

        raise KeyError(f"{attrname!r}")

    def get(self, attrname: str, default_value: Optional[Any] = None) -> Optional[Any]:
        """
        Get a configuration setting property by name.

        Args:
            attrname (str): The configuration setting key.
            default_value (Optional[Any]): The value to return if the key does
              not exist. Defaults to ``None``.

        Returns:
            Optional[Any]: The default value if the key is not in the config, the value otherwise.
        """

        if attrname in self.__slots__:
            return getattr(self, attrname)

        return default_value


class ConfigDict(ConfigItem):
    """
    A config class that is generic and key-value based.
    """

    def __post_init__(self):
        raise ValueError("Do not use this class directly!")
