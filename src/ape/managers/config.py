import os
from contextlib import contextmanager
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, Generator, List, Optional, Union

from ethpm_types import PackageMeta
from pydantic import RootModel, model_validator

from ape.api import ConfigDict, DependencyAPI, PluginConfig
from ape.exceptions import ConfigError
from ape.logging import logger
from ape.utils import BaseInterfaceModel, load_config, log_instead_of_fail

if TYPE_CHECKING:
    from .project import ProjectManager


CONFIG_FILE_NAME = "ape-config.yaml"


class DeploymentConfig(PluginConfig):
    address: Union[str, bytes]
    contract_type: str


class DeploymentConfigCollection(RootModel[dict]):
    @model_validator(mode="before")
    @classmethod
    def validate_deployments(cls, data: Dict, info):
        valid_ecosystems = data.pop("valid_ecosystems", {})
        valid_networks = data.pop("valid_networks", {})
        valid_data: Dict = {}
        for ecosystem_name, networks in data.items():
            if ecosystem_name not in valid_ecosystems:
                logger.warning(f"Invalid ecosystem '{ecosystem_name}' in deployments config.")
                continue

            ecosystem = valid_ecosystems[ecosystem_name]
            for network_name, contract_deployments in networks.items():
                if network_name not in valid_networks:
                    logger.warning(f"Invalid network '{network_name}' in deployments config.")
                    continue

                valid_deployments = []
                for deployment in [d for d in contract_deployments]:
                    if not (address := deployment.get("address")):
                        logger.warning(
                            f"Missing 'address' field in deployment "
                            f"(ecosystem={ecosystem_name}, network={network_name})"
                        )
                        continue

                    valid_deployment = {**deployment}
                    try:
                        valid_deployment["address"] = ecosystem.decode_address(address)
                    except ValueError as err:
                        logger.warning(str(err))

                    valid_deployments.append(valid_deployment)

                valid_data[ecosystem_name] = {
                    **valid_data.get(ecosystem_name, {}),
                    network_name: valid_deployments,
                }

        return valid_data


class ConfigManager(BaseInterfaceModel):
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
    """The path to the ``ape`` directory such as ``$HOME/.ape``."""

    REQUEST_HEADER: Dict

    PROJECT_FOLDER: Path
    """The path to the ``ape`` project."""

    name: str = ""
    """The name of the project."""

    version: str = ""
    """The project's version."""

    meta: PackageMeta = PackageMeta()
    """Metadata about the project."""

    contracts_folder: Path = None  # type: ignore
    """
    The path to the project's ``contracts/`` directory
    (differs by project structure).
    """

    dependencies: List[DependencyAPI] = []
    """A list of project dependencies."""

    deployments: Optional[DeploymentConfigCollection] = None
    """A dict of contract deployments by address and contract type."""

    default_ecosystem: str = "ethereum"
    """The default ecosystem to use. Defaults to ``"ethereum"``."""

    _config_override: Dict[str, Any] = {}
    """Adhoc config overrides."""

    _cached_configs: Dict[str, Dict[str, Any]] = {}

    @model_validator(mode="before")
    @classmethod
    def check_config_for_extra_fields(cls, values: Dict[str, Any]) -> Dict[str, Any]:
        extra = [key for key in values.keys() if key not in cls.model_fields]
        if extra:
            logger.warning(f"Unprocessed extra config fields not set '{extra}'.")

        return values

    @model_validator(mode="after")
    @classmethod
    def load_configs(cls, cm):
        return cm.load()

    @property
    def packages_folder(self) -> Path:
        self.dependency_manager.packages_folder.mkdir(parents=True, exist_ok=True)
        return self.dependency_manager.packages_folder

    @property
    def _project_key(self) -> str:
        return self.PROJECT_FOLDER.stem

    @property
    def _project_configs(self) -> Dict[str, Any]:
        return self._cached_configs.get(self._project_key, {})

    @property
    def _plugin_configs(self) -> Dict[str, PluginConfig]:
        if cache := self._cached_configs.get(self._project_key):
            self.name = cache.get("name", "")
            self.version = cache.get("version", "")
            self.default_ecosystem = cache.get("default_ecosystem", "ethereum")
            self.meta = PackageMeta.model_validate(cache.get("meta", {}))
            self.dependencies = cache.get("dependencies", [])
            self.deployments = cache.get("deployments", {})
            self.contracts_folder = cache.get("contracts_folder", self.PROJECT_FOLDER / "contracts")
            return cache

        # First, load top-level configs. Then, load all the plugin configs.
        # The configs are popped off the dict for checking if all configs were processed.

        configs = {}
        global_config_file = self.DATA_FOLDER / CONFIG_FILE_NAME
        global_config = load_config(global_config_file) if global_config_file.is_file() else {}
        config_file = self.PROJECT_FOLDER / CONFIG_FILE_NAME

        # NOTE: It is critical that we read in global config values first
        # so that project config values will override them as-needed.
        project_config = load_config(config_file) if config_file.is_file() else {}
        user_config = merge_configs(global_config, project_config, self._config_override)

        self.name = configs["name"] = user_config.pop("name", "")
        self.version = configs["version"] = user_config.pop("version", "")
        meta_dict = user_config.pop("meta", {})
        meta_obj = PackageMeta.model_validate(meta_dict)
        configs["meta"] = meta_dict
        self.meta = meta_obj
        self.default_ecosystem = configs["default_ecosystem"] = user_config.pop(
            "default_ecosystem", "ethereum"
        )

        dependencies = user_config.pop("dependencies", []) or []
        if not isinstance(dependencies, list):
            raise ConfigError("'dependencies' config item must be a list of dicts.")

        decode = self.dependency_manager.decode_dependency
        configs["dependencies"] = [decode(dep) for dep in dependencies]
        self.dependencies = configs["dependencies"]

        # NOTE: It is okay for this directory not to exist at this point.
        contracts_folder = user_config.pop(
            "contracts_folder", user_config.pop("contracts-folder", None)
        )
        contracts_folder = (
            (self.PROJECT_FOLDER / Path(contracts_folder)).expanduser().resolve()
            if contracts_folder
            else self.PROJECT_FOLDER / "contracts"
        )

        self.contracts_folder = configs["contracts_folder"] = contracts_folder
        deployments = user_config.pop("deployments", {})
        valid_ecosystems = dict(self.plugin_manager.ecosystems)
        valid_network_names = [n[1] for n in [e[1] for e in self.plugin_manager.networks]]
        self.deployments = configs["deployments"] = DeploymentConfigCollection(
            root={
                **deployments,
                "valid_ecosystems": valid_ecosystems,
                "valid_networks": valid_network_names,
            }
        )

        ethereum_config_cls = None
        for plugin_name, config_class in self.plugin_manager.config_class:
            # `or {}` to handle the case when the empty config is `None`.
            user_override = user_config.pop(plugin_name, {}) or {}

            # Store ethereum's class for custom network config loading.
            if plugin_name == "ethereum":
                ethereum_config_cls = config_class

            if config_class != ConfigDict:
                config = config_class.from_overrides(  # type: ignore
                    # NOTE: Will raise if improperly provided keys
                    user_override,
                    # NOTE: Sending ourselves in case the PluginConfig needs access to the root
                    #       config vars.
                    config_manager=self,
                )
            else:
                # NOTE: Just use it directly as a dict if `ConfigDict` is passed
                config = user_override

            configs[plugin_name] = config

        # Load custom ecosystem configs.
        if ethereum_config_cls is not None and user_config:
            custom_ecosystem_names = {
                x.get("ecosystem")
                for x in configs.get("networks", {}).get("custom", [])
                if x.get("ecosystem") and x["ecosystem"] not in configs
            }
            custom_ecosystem_configs = {
                n: cfg for n, cfg in user_config.items() if n in custom_ecosystem_names
            }

            for ecosystem_name, cfg in custom_ecosystem_configs.items():
                config = ethereum_config_cls.from_overrides(cfg)  # type: ignore
                configs[ecosystem_name] = config
                del user_config[ecosystem_name]

        remaining_keys = user_config.keys()
        if len(remaining_keys) > 0:
            remaining_keys_str = ", ".join(remaining_keys)
            logger.warning(
                f"Unprocessed plugin config(s): {remaining_keys_str}. "
                "Plugins may not be installed yet or keys may be mis-spelled."
            )

        self._cached_configs[self._project_key] = configs
        return configs

    @log_instead_of_fail(default="<ConfigManager>")
    def __repr__(self) -> str:
        return f"<{ConfigManager.__name__} project={self.PROJECT_FOLDER.name}>"

    def load(self, force_reload: bool = False, **overrides) -> "ConfigManager":
        """
        Load the user config file and return this class.
        """

        if force_reload:
            self._cached_configs = {}

        self._config_override = overrides or {}
        _ = self._plugin_configs

        return self

    def get_config(self, plugin_name: str) -> PluginConfig:
        """
        Get a plugin config.

        Args:
            plugin_name (str): The name of the plugin to get the config for.

        Returns:
            :class:`~ape.api.config.PluginConfig`
        """

        self.load()  # Only loads if it needs to.

        if plugin_name not in self._plugin_configs:
            # plugin has no registered config class, so return empty config
            return PluginConfig()

        return self._plugin_configs[plugin_name]

    @contextmanager
    def using_project(
        self, project_folder: Path, contracts_folder: Optional[Path] = None, **config
    ) -> Generator["ProjectManager", None, None]:
        """
        Temporarily change the project context.

        Usage example::

            from pathlib import Path
            from ape import config, Project

            project_path = Path("path/to/project")
            contracts_path = project_path / "contracts"

            with config.using_project(project_path):
                my_project = Project(project_path)

        Args:
            project_folder (pathlib.Path): The path of the context's project.
            contracts_folder (Optional[pathlib.Path]): The path to the context's source files.
              Defaults to ``<project_path>/contracts``.

        Returns:
            Generator
        """

        initial_project_folder = self.project_manager.path
        initial_contracts_folder = self.contracts_folder

        if initial_project_folder == project_folder and (
            not contracts_folder or initial_contracts_folder == contracts_folder
        ):
            # Already in project.
            yield self.project_manager
            return

        self.PROJECT_FOLDER = project_folder

        if isinstance(contracts_folder, str):
            contracts_folder = (project_folder / contracts_folder).expanduser().resolve()
        elif isinstance(contracts_folder, Path):
            contracts_folder = contracts_folder
        else:
            contracts_folder = project_folder / "contracts"

        self.contracts_folder = contracts_folder
        self.project_manager.path = project_folder
        os.chdir(project_folder)
        clean_config = False

        try:
            # Process and reload the project's configuration
            project = self.project_manager.get_project(
                project_folder, contracts_folder=contracts_folder
            )
            # Ensure this ends up in the project's config.
            if "contracts_folder" not in config:
                config["contracts_folder"] = contracts_folder

            clean_config = project.process_config_file(**config)
            self.load(force_reload=True)
            yield self.project_manager

        finally:
            temp_project_path = self.project_manager.path
            self.PROJECT_FOLDER = initial_project_folder
            self.contracts_folder = initial_contracts_folder
            self.project_manager.path = initial_project_folder

            if initial_project_folder.is_dir():
                os.chdir(initial_project_folder)

            config_file = temp_project_path / CONFIG_FILE_NAME
            if clean_config and config_file.is_file():
                config_file.unlink()


def merge_configs(*cfgs) -> Dict:
    if len(cfgs) == 0:
        return {}
    elif len(cfgs) == 1:
        return cfgs[0]

    new_base = _merge_configs(cfgs[0], cfgs[1])
    return merge_configs(new_base, *cfgs[2:])


def _merge_configs(base: Dict, secondary: Dict) -> Dict:
    result: Dict = {}

    # Short circuits
    if not base and not secondary:
        return result
    elif not base:
        return secondary
    elif not secondary:
        return base

    for key, value in base.items():
        if key not in secondary:
            result[key] = value

        elif not isinstance(value, dict):
            # Is a primitive value found in both configs.
            # Must use the second one.
            result[key] = secondary[key]

        else:
            # Merge the dictionaries.
            sub = _merge_configs(base[key], secondary[key])
            result[key] = sub

    # Add missed keys from secondary.
    for key, value in secondary.items():
        if key not in base:
            result[key] = value

    return result
