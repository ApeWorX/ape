from typing import Dict

from ape.api import ConfigItem


class Config(ConfigItem):
    default_ecosystem: str = "ethereum"
    development: Dict = {"default_provider": "test"}
