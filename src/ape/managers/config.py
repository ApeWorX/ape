import os
from contextlib import contextmanager
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, Generator, List, Optional, Union

from pydantic import root_validator

from ape.api import ConfigDict, DependencyAPI, PluginConfig
from ape.exceptions import ConfigError, NetworkError
from ape.logging import logger
from ape.utils import BaseInterfaceModel, load_config

if TYPE_CHECKING:
    from .project import ProjectManager

from ethpm_types import PackageMeta

CONFIG_FILE_NAME = "ape-config.yaml"


class DeploymentConfig(PluginConfig):
    address: Union[str, bytes]
    contract_type: str


class CompilerConfig(PluginConfig):
    ignore_files: List[str] = ["*package.json", "*package-lock.json", "*tsconfig.json"]
    """List of globular files to ignore"""


class DeploymentConfigCollection(dict):
    def __init__(self, data: Dict, valid_ecosystems: Dict, valid_networks: List[str]):
        for ecosystem_name, networks in data.items():
            if ecosystem_name not in valid_ecosystems:
                logger.warning(f"Invalid ecosystem '{ecosystem_name}' in deployments config.")
                continue

            ecosystem = valid_ecosystems[ecosystem_name]
            for network_name, contract_deployments in networks.items():
                if network_name not in valid_networks:
                    logger.warning(f"Invalid network '{network_name}' in deployments config.")
                    continue

                for deployment in [d for d in contract_deployments]:
                    address = deployment.get("address", None)
                    if "address" not in deployment:
                        logger.warning(
                            f"Missing 'address' field in deployment "
                            f"(ecosystem={ecosystem_name}, network={network_name})"
                        )
                        continue

                    try:
                        deployment["address"] = ecosystem.decode_address(address)
                    except ValueError as err:
                        logger.warning(str(err))

        super().__init__(data)


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

    compiler: CompilerConfig = CompilerConfig()
    """Global compiler information."""

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

    _cached_configs: Dict[str, Dict[str, Any]] = {}

    @root_validator(pre=True)
    def check_config_for_extra_fields(cls, values: Dict[str, Any]) -> Dict[str, Any]:
        extra = [key for key in values.keys() if key not in cls.__fields__]
        if extra:
            logger.warning(f"Unprocessed extra config fields not set '{extra}'.")

        return values

    @property
    def packages_folder(self) -> Path:
        path = self.DATA_FOLDER / "packages"
        path.mkdir(parents=True, exist_ok=True)
        return path

    @property
    def _plugin_configs(self) -> Dict[str, PluginConfig]:
        project_name = self.PROJECT_FOLDER.stem
        if project_name in self._cached_configs:
            cache = self._cached_configs[project_name]
            self.name = cache.get("name", "")
            self.version = cache.get("version", "")
            self.default_ecosystem = cache.get("default_ecosystem", "ethereum")
            self.meta = PackageMeta.parse_obj(cache.get("meta", {}))
            self.dependencies = cache.get("dependencies", [])
            self.deployments = cache.get("deployments", {})
            self.contracts_folder = cache.get("contracts_folder", self.PROJECT_FOLDER / "contracts")
            self.compiler = CompilerConfig.parse_obj(cache.get("compiler", {}))
            return cache

        # First, load top-level configs. Then, load all the plugin configs.
        # The configs are popped off the dict for checking if all configs were processed.

        configs = {}
        config_file = self.PROJECT_FOLDER / CONFIG_FILE_NAME
        user_config = load_config(config_file) if config_file.is_file() else {}
        self.name = configs["name"] = user_config.pop("name", "")
        self.version = configs["version"] = user_config.pop("version", "")
        meta_dict = user_config.pop("meta", {})
        meta_obj = PackageMeta.parse_obj(meta_dict)
        configs["meta"] = meta_dict
        self.meta = meta_obj
        self.default_ecosystem = configs["default_ecosystem"] = user_config.pop(
            "default_ecosystem", "ethereum"
        )
        compiler_dict = user_config.pop("compiler", CompilerConfig().dict())
        configs["compiler"] = compiler_dict
        self.compiler = CompilerConfig(**compiler_dict)

        try:
            self.network_manager.set_default_ecosystem(self.default_ecosystem)
        except NetworkError as err:
            logger.warning(str(err))

        dependencies = user_config.pop("dependencies", []) or []
        if not isinstance(dependencies, list):
            raise ConfigError("'dependencies' config item must be a list of dicts.")

        decode = self.dependency_manager.decode_dependency
        configs["dependencies"] = [decode(dep) for dep in dependencies]
        self.dependencies = configs["dependencies"]

        # NOTE: It is okay for this directory not to exist at this point.
        contracts_folder = (
            Path(user_config.pop("contracts_folder")).expanduser().resolve()
            if "contracts_folder" in user_config
            else self.PROJECT_FOLDER / "contracts"
        )
        self.contracts_folder = configs["contracts_folder"] = contracts_folder

        deployments = user_config.pop("deployments", {})
        valid_ecosystems = dict(self.plugin_manager.ecosystems)
        valid_network_names = [n[1] for n in [e[1] for e in self.plugin_manager.networks]]
        self.deployments = configs["deployments"] = DeploymentConfigCollection(
            deployments, valid_ecosystems, valid_network_names
        )

        for plugin_name, config_class in self.plugin_manager.config_class:
            user_override = user_config.pop(plugin_name, {})
            if config_class != ConfigDict:
                # NOTE: Will raise if improperly provided keys
                config = config_class.from_overrides(user_override)  # type: ignore
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

        self._cached_configs[project_name] = configs
        return configs

    def __repr__(self):
        return f"<{self.__class__.__name__} project={self.PROJECT_FOLDER.name}>"

    def load(self, force_reload: bool = False) -> "ConfigManager":
        """
        Load the user config file and return this class.
        """

        if force_reload:
            self._cached_configs = {}

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
        self, project_folder: Path, contracts_folder: Optional[Path] = None
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
        contracts_folder = contracts_folder or project_folder / "contracts"
        initial_project_folder = self.PROJECT_FOLDER
        initial_contracts_folder = self.contracts_folder

        self.PROJECT_FOLDER = project_folder
        self.contracts_folder = contracts_folder
        self.project_manager.path = project_folder
        os.chdir(project_folder)

        try:
            self.load(force_reload=True)
            yield self.project_manager
        finally:
            self.PROJECT_FOLDER = initial_project_folder
            self.contracts_folder = initial_contracts_folder
            self.project_manager.path = initial_project_folder

            if initial_project_folder.is_dir():
                os.chdir(initial_project_folder)
