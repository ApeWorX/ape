import json
from pathlib import Path
from typing import Dict, List

from dataclassy import dataclass

from ape.api.config import ConfigDict, ConfigItem
from ape.plugins import PluginManager
from ape.utils import load_config

CONFIG_FILE_NAME = "ape-config.yaml"


@dataclass
class ConfigManager:
    DATA_FOLDER: Path
    REQUEST_HEADER: Dict
    PROJECT_FOLDER: Path
    name: str = ""
    version: str = ""
    dependencies: List[str] = []
    plugin_manager: PluginManager
    _plugin_configs: Dict[str, ConfigItem] = dict()

    def __post_init__(self):
        config_file = self.PROJECT_FOLDER / CONFIG_FILE_NAME

        if config_file.exists():
            user_config = load_config(config_file)
        else:
            user_config = {}

        # Top level config items
        self.name = user_config.pop("name", "")
        self.version = user_config.pop("version", "")
        self.dependencies = user_config.pop("dependencies", [])

        for plugin_name, config_class in self.plugin_manager.config_class:
            # NOTE: `dict.pop()` is used for checking if all config was processed
            user_override = user_config.pop(plugin_name, {})

            if config_class != ConfigDict:
                # NOTE: Will raise if improperly provided keys
                config = config_class(**user_override)

                # NOTE: Should raise if settings violate some sort of plugin requirement
                config.validate_config()

            else:
                # NOTE: Just use it directly as a dict if `ConfigDict` is passed
                config = user_override

            self._plugin_configs[plugin_name] = config

        if len(user_config.keys()) > 0:
            raise Exception("Unprocessed config items")

    def get_config(self, plugin_name: str) -> ConfigItem:
        if plugin_name not in self._plugin_configs:
            # plugin has no registered config class, so return empty config
            return ConfigItem()

        return self._plugin_configs[plugin_name]

    def serialize(self) -> Dict:
        project_config = dict()

        for name, config in self._plugin_configs.items():
            # NOTE: `config` is either `ConfigItem` or `dict`
            project_config[name] = config.serialize() if isinstance(config, ConfigItem) else config

        return project_config

    def __str__(self) -> str:
        return json.dumps(self.serialize())
