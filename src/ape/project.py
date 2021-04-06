import json
from pathlib import Path
from typing import Dict

from dataclassy import dataclass

from ape.api.config import ConfigItem
from ape.plugins import clean_plugin_name, plugin_manager

from .utils import load_config


class Config:
    @classmethod
    def default(cls):
        return cls({})

    @classmethod
    def from_config_file(cls, config_file: Path):
        cls(load_config(config_file))

    def __init__(self, user_config: Dict):
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


CONFIG_FILE_NAME = "ape-config.yaml"


@dataclass
class Project:
    path: Path = Path.cwd()
    config: Config = None  # type: ignore

    depedendencies: Dict[str, "Project"] = dict()

    def __init__(self):
        if self.config is None:
            config_file = self.path / CONFIG_FILE_NAME
            if config_file.exists():
                self.config = Config.from_config_file(config_file)
            else:
                self.config = Config.default()

    def __str__(self) -> str:
        return f'Project("{self.path}")'

    def _cache_folder(self) -> Path:
        folder = self.path / ".build"
        # NOTE: If we use the cache folder, we expect it to exist
        folder.mkdir(exist_ok=True)
        return folder

    # NOTE: Using these paths should handle the case when the folder doesn't exist
    def _contracts_folder(self) -> Path:
        return self.path / "contracts"

    def _interfaces_folder(self) -> Path:
        return self.path / "interfaces"

    def _scripts_folder(self) -> Path:
        return self.path / "scripts"

    def _tests_folder(self) -> Path:
        return self.path / "tests"

    # TODO: Add `contracts` property, that gives attrdict of all compiled contract types in project
    # TODO: Add `manifest` property, that fully compiles and assembles the EthPM Manifest
    # NOTE: If project is a dependency, then the manifest doesn't need to be assembled
