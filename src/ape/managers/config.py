import json
from pathlib import Path
from typing import Dict

from dataclassy import dataclass

from ape.api.config import ConfigItem
from ape.plugins import PluginManager, clean_plugin_name
from ape.utils import load_config

CONFIG_FILE_NAME = "ape-config.yaml"


@dataclass
class ConfigManager:
    DATA_FOLDER: Path
    REQUEST_HEADER: Dict
    PROJECT_FOLDER: Path
    plugin_manager: PluginManager
    _plugin_configs: Dict[str, ConfigItem] = dict()

    def __init__(self):
        config_file = self.PROJECT_FOLDER / CONFIG_FILE_NAME
        if config_file.exists():
            user_config = load_config(config_file)
        else:
            user_config = {}

        for hookimpl in self.plugin_manager.hook.config_class.get_hookimpls():
            plugin_name = clean_plugin_name(hookimpl.plugin_name)
            config_class = hookimpl.plugin.config_class()

            if plugin_name in user_config:
                user_override = user_config[plugin_name]
                del user_config[plugin_name]  # For checking if all config was processed
            else:
                user_override = {}

            # NOTE: Will raise if improperly provided keys
            config = config_class(**user_override)

            # NOTE: Should raise if settings violate some sort of plugin requirement
            config.validate_config()

            self._plugin_configs[plugin_name] = config

        if len(user_config.keys()) > 0:
            raise  # Unprocessed config items

    def get_config(self, plugin_name: str) -> ConfigItem:
        if plugin_name not in self._plugin_configs:
            # plugin has no registered config class, so return empty config
            return ConfigItem()

        return self._plugin_configs[plugin_name]

    def serialize(self) -> Dict:
        project_config = dict()

        for name, config in self._plugin_configs.items():
            project_config[name] = config.serialize()

        return project_config

    def __str__(self) -> str:
        return json.dumps(self.serialize())
