from typing import Dict

from ape.api import ConfigItem


class Config(ConfigItem):
    development: Dict = {"default_provider": "test"}
