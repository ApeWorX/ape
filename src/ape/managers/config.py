import json
from pathlib import Path
from typing import Any, Dict, List

from pydantic import BaseSettings

from ape.api.config import PluginConfig, UnprocessedConfig
from ape.exceptions import ConfigError
from ape.plugins import PluginManager
from ape.utils import cached_property, load_config

CONFIG_FILE_NAME = "ape-config.yaml"


class ConfigManager(BaseSettings):
    DATA_FOLDER: Path
    REQUEST_HEADER: Dict
    PROJECT_FOLDER: Path
    name: str = ""
    version: str = ""
    dependencies: List[str] = []
    plugin_manager: PluginManager

    class Config:
        keep_untouched = (cached_property,)

    # NOTE: Due to https://github.com/samuelcolvin/pydantic/issues/1241
    #       we have to add this cached property workaround in order to avoid this error:
    #
    #           TypeError: cannot pickle '_thread.RLock' object

    @cached_property
    def _user_config(self) -> dict:
        config_file = self.PROJECT_FOLDER / CONFIG_FILE_NAME

        if config_file.exists():
            return load_config(config_file)

        else:
            return {}

    @cached_property
    def _plugin_configs(self) -> Dict[str, PluginConfig]:
        # NOTE: `dict.pop()` is used for checking if all config was processed
        user_config = self._user_config

        # Top level config items
        self.name = user_config.pop("name", "")
        self.version = user_config.pop("version", "")
        self.dependencies = user_config.pop("dependencies", {})

        plugin_configs = {
            # NOTE: Will raise if improperly provided keys
            plugin_name: config_class(**user_config.pop(plugin_name, {}))
            for plugin_name, (config_class,) in self.plugin_manager.config_class
        }

        if len(user_config.keys()) > 0:
            raise ConfigError("Unprocessed config items.")

        return plugin_configs

    def get_config(self, plugin_name: str) -> PluginConfig:
        if plugin_name in self._plugin_configs:
            return self._plugin_configs[plugin_name]

        elif plugin_name in self._user_config:
            return UnprocessedConfig(self._user_config[plugin_name])

        else:
            return UnprocessedConfig()  # Empty config for this plugin

    def dict(self, *args, **kwargs) -> Dict:
        project_config: Dict[str, Any] = {
            "name": self.name,
            "version": self.version,
            "dependencies": self.dependencies,
        }

        for name, config in self._plugin_configs.items():
            project_config[name] = config.dict()

        return project_config

    def __str__(self) -> str:
        return json.dumps(self.dict())
