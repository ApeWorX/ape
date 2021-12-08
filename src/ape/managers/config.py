import json
from pathlib import Path
from typing import Dict, List

from pydantic import BaseSettings

from ape.api.config import PluginConfig, UnprocessedConfig
from ape.exceptions import ConfigError
from ape.plugins import PluginManager
from ape.utils import load_config

CONFIG_FILE_NAME = "ape-config.yaml"


class ConfigManager(BaseSettings):
    DATA_FOLDER: Path
    REQUEST_HEADER: Dict
    PROJECT_FOLDER: Path
    name: str = ""
    version: str = ""
    dependencies: List[str] = []
    plugin_manager: PluginManager
    _plugin_configs: Dict[str, PluginConfig] = dict()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        config_file = self.PROJECT_FOLDER / CONFIG_FILE_NAME

        if config_file.exists():
            user_config = load_config(config_file)
        else:
            user_config = {}

        # Top level config items
        self.name = user_config.pop("name", "")
        self.version = user_config.pop("version", "")
        self.dependencies = user_config.pop("dependencies", {})

        for plugin_name, config_class in self.plugin_manager.config_class:
            # NOTE: `dict.pop()` is used for checking if all config was processed
            user_override = user_config.pop(plugin_name, {})

            # NOTE: Will raise if improperly provided keys
            config = config_class(**user_override)

            self._plugin_configs[plugin_name] = config

        if len(user_config.keys()) > 0:
            raise ConfigError("Unprocessed config items.")

    def get_config(self, plugin_name: str) -> PluginConfig:
        if plugin_name in self._plugin_configs:
            return self._plugin_configs[plugin_name]

        else:
            return UnprocessedConfig()

    def dict(self, *args, **kwargs) -> Dict:
        project_config = self.dict(*args, **kwargs)

        for name, config in self._plugin_configs.items():
            project_config[name] = config.dict()

        return project_config

    def __str__(self) -> str:
        return json.dumps(self.dict())
