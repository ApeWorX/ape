import json
from pathlib import Path
from typing import Dict, Optional

from ape.api.config import ConfigItem
from ape.plugins import clean_plugin_name, plugin_manager

from .utils import load_config


class ProjectConfig:
    def __init__(self, config_file: Path):
        user_config = load_config(config_file)
        plugin_configs: Dict[str, ConfigItem] = {}

        for hookimpl in plugin_manager.hook.config_class.get_hookimpls():
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

            plugin_configs[plugin_name] = config

        if len(user_config.keys()) > 0:
            raise  # Unprocessed config items

        self._plugin_configs = plugin_configs

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


class Project:
    def __init__(self, project_path: Path = Path.cwd()):
        self._path = project_path
        self._config: Optional[ProjectConfig] = None

    def __str__(self) -> str:
        return f'{self.__class__.__name__}("{self._path}")'

    @property
    def config(self) -> ProjectConfig:
        if self._config is None:
            self._config = ProjectConfig(self._path / "ape-config.yaml")
        return self._config

    @property
    def _cache_folder(self) -> Path:
        cache_folder = self._path / ".build"
        cache_folder.mkdir(exist_ok=True)
        return cache_folder

    @property
    def _contracts_folder(self) -> Path:
        contracts_folder = self._path / "contracts"
        if contracts_folder.exists():
            return contracts_folder
        else:
            raise  # No contracts folder in project

    # TODO: Add `contracts` property, that gives attrdict of all compiled contract types in project
    # TODO: Add `manifest` property, that fully compiles and assembles the EthPM Manifest
    # NOTE: If project is a dependency, then the manifest doesn't need to be assembled
