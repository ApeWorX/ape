import json
from pathlib import Path
from typing import Dict, List, Union

from dataclassy import dataclass

from ape.api import ConfigDict, ConfigItem
from ape.convert import to_address
from ape.exceptions import ConfigError
from ape.logging import logger
from ape.plugins import PluginManager
from ape.utils import load_config

CONFIG_FILE_NAME = "ape-config.yaml"


class DeploymentConfig(ConfigItem):
    address: Union[str, bytes]
    contract_type: str


@dataclass
class ConfigManager:
    """
    The singleton responsible for managing the ``ape-config.yaml`` project file.
    The config manager is useful for loading plugin configurations which contain
    settings that determine how ``ape`` functions. When developing plugins,
    you may want to have settings that control how the plugin works. When developing
    scripts in a project, you may want to parametrize how it runs. The config manager
    is how you can access those settings at runtime.

    Access the ``ConfigManager`` from the ``ape`` namespace directly via:

    Usage example::

        from ape import config  # "config" is the ConfigManager singleton

        # Example: load the "ape-test" plugin and access the mnemonic
        test_mnemonic = config.get_config("test").mnemonic
    """

    DATA_FOLDER: Path
    REQUEST_HEADER: Dict
    PROJECT_FOLDER: Path
    name: str = ""
    version: str = ""
    dependencies: Dict[str, str] = {}
    deployments: Dict[str, Dict[str, List[DeploymentConfig]]] = {}
    plugin_manager: PluginManager
    _plugin_configs_by_project: Dict[str, Dict[str, ConfigItem]] = {}

    @property
    def packages_folder(self) -> Path:
        path = self.DATA_FOLDER / "packages"
        path.mkdir(parents=True, exist_ok=True)
        return path

    @property
    def _plugin_configs(self) -> Dict[str, ConfigItem]:
        # This property is cached per active project.
        project_name = self.PROJECT_FOLDER.stem
        if project_name in self._plugin_configs_by_project:
            return self._plugin_configs_by_project[project_name]

        configs = {}
        config_file = self.PROJECT_FOLDER / CONFIG_FILE_NAME
        user_config = load_config(config_file) if config_file.exists() else {}

        # Top level config items
        self.name = user_config.pop("name", "")
        self.version = user_config.pop("version", "")
        self.dependencies = user_config.pop("dependencies", {})

        # Sanitize deployment addresses.
        deployments = user_config.pop("deployments", {})
        valid_ecosystem_names = [e[0] for e in self.plugin_manager.ecosystems]
        for ecosystem_name, networks in deployments.items():
            if ecosystem_name not in valid_ecosystem_names:
                raise ConfigError(f"Invalid ecosystem '{ecosystem_name}' in deployments config.")

            valid_network_names = [n[1] for n in [e[1] for e in self.plugin_manager.networks]]
            for network_name, contract_deployments in networks.items():
                if network_name not in valid_network_names:
                    raise ConfigError(f"Invalid network '{network_name}' in deployments config.")

                for deployment in [d for d in contract_deployments]:
                    if "address" not in deployment:
                        raise ConfigError(
                            f"Missing 'address' field in deployment "
                            f"(ecosystem={ecosystem_name}, network={network_name})"
                        )

                    address = deployment["address"]

                    try:
                        deployment["address"] = to_address(address)
                    except ValueError as err:
                        raise ConfigError(str(err)) from err

        self.deployments = deployments

        for plugin_name, config_class in self.plugin_manager.config_class:
            # NOTE: `dict.pop()` is used for checking if all config was processed
            user_override = user_config.pop(plugin_name, {})

            if config_class != ConfigDict:
                # NOTE: Will raise if improperly provided keys
                config = config_class(**user_override)  # type: ignore

                # NOTE: Should raise if settings violate some sort of plugin requirement
                config.validate_config()

            else:
                # NOTE: Just use it directly as a dict if `ConfigDict` is passed
                config = user_override

            configs[plugin_name] = config

        remaining_keys = user_config.keys()
        if len(remaining_keys) > 0:
            remaining_keys_str = ", ".join(remaining_keys)
            logger.warning(
                f"Unprocessed plugin config(s): {remaining_keys_str}. "
                "Plugins may not be installed yet or keys may be mis-spelled."
            )

        self._plugin_configs_by_project[project_name] = configs
        return configs

    def __repr__(self):
        return "<ConfigManager>"

    def load(self) -> "ConfigManager":
        """
        Load the user config file and return this class.
        """

        _ = self._plugin_configs
        return self

    def get_config(self, plugin_name: str) -> ConfigItem:
        """
        Get a plugin config.

        Args:
            plugin_name (str): The name of the plugin to get the config for.

        Returns:
            :class:`~ape.api.config.ConfigItem`
        """

        if plugin_name not in self._plugin_configs:
            # plugin has no registered config class, so return empty config
            return ConfigItem()

        return self._plugin_configs[plugin_name]

    def serialize(self) -> Dict:
        """
        Convert the project config file, ``ape-config.yaml``, to a dictionary.

        Returns:
            dict
        """

        project_config = dict()

        for name, config in self._plugin_configs.items():
            # NOTE: `config` is either `ConfigItem` or `dict`
            project_config[name] = config.serialize() if isinstance(config, ConfigItem) else config

        return project_config

    def __str__(self) -> str:
        """
        The JSON-text version of the project config data.

        Returns:
            str
        """

        return json.dumps(self.serialize())
