import os
from collections.abc import Iterable, Iterator
from enum import Enum
from functools import cached_property
from pathlib import Path
from typing import Any, Optional, TypeVar, cast

import yaml
from ethpm_types import PackageManifest, PackageMeta, Source
from pydantic import ConfigDict, Field, ValidationError, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from ape.exceptions import ConfigError
from ape.logging import logger
from ape.types.address import AddressType
from ape.utils.basemodel import (
    ExtraAttributesMixin,
    ExtraModelAttributes,
    ManagerAccessMixin,
    _assert_not_ipython_check,
    get_attribute_with_extras,
    only_raise_attribute_error,
)
from ape.utils.misc import load_config
from ape.utils.os import clean_path

ConfigItemType = TypeVar("ConfigItemType")


class ConfigEnum(str, Enum):
    """
    A configuration `Enum <https://docs.python.org/3/library/enum.html>`__ type.
    Use this to limit the values of a config item, such as colors ``"RED"``, ``"BLUE"``,
    ``"GREEN"``, rather than any arbitrary ``str``.

    Usage example::

            class MyEnum(ConfigEnum):
                FOO = "FOO"
                BAR = "BAR"

            class MyConfig(PluginConfig):
                my_enum: MyEnum

            model = MyConfig(my_enum="FOO")

    """


def _find_config_yaml_files(base_path: Path) -> list[Path]:
    """
    Find all ape config file in the given path.
    """
    found: list[Path] = []
    if (base_path / "ape-config.yaml").is_file():
        found.append(base_path / "ape-config.yaml")
    if (base_path / "ape-config.yml").is_file():
        found.append(base_path / "ape-config.yml")

    return found


class PluginConfig(BaseSettings):
    """
    A base plugin configuration class. Each plugin that includes
    a config API must register a subclass of this class.
    """

    model_config = SettingsConfigDict(extra="allow")

    @classmethod
    def from_overrides(
        cls, overrides: dict, plugin_name: Optional[str] = None, project_path: Optional[Path] = None
    ) -> "PluginConfig":
        default_values = cls().model_dump()

        def update(root: dict, value_map: dict):
            for key, val in value_map.items():
                if isinstance(val, dict) and key in root and isinstance(root[key], dict):
                    root[key] = update(root[key], val)
                else:
                    root[key] = val

            return root

        data = update(default_values, overrides)
        try:
            return cls.model_validate(data)
        except ValidationError as err:
            plugin_name = plugin_name or cls.__name__.replace("Config", "").lower()
            if problems := cls._find_plugin_config_problems(
                err, plugin_name, project_path=project_path
            ):
                raise ConfigError(problems) from err
            else:
                raise ConfigError(str(err)) from err

    @classmethod
    def _find_plugin_config_problems(
        cls, err: ValidationError, plugin_name: str, project_path: Optional[Path] = None
    ) -> Optional[str]:
        # Attempt showing line-nos for failed plugin config validation.
        # This is trickier than root-level data since by this time, we
        # no longer are aware of which files are responsible for which config.
        ape = ManagerAccessMixin

        # First, try checking the root config file ALONE. It is important to do
        # w/o any data from the project-level config to isolate the source of the problem.
        raw_global_data = ape.config_manager.global_config.model_dump(by_alias=True)
        if plugin_name in raw_global_data:
            try:
                cls.model_validate(raw_global_data[plugin_name])
            except Exception:
                if problems := cls._find_plugin_config_problems_from_file(
                    err, ape.config_manager.DATA_FOLDER
                ):
                    return problems

        # No issues found with global; try the local project.
        # NOTE: No need to isolate project-data w/o root-data because we have already
        #  determined root-level data is OK.
        project_path = project_path or ape.local_project.path
        if problems := cls._find_plugin_config_problems_from_file(err, project_path):
            return problems

        return None

    @classmethod
    def _find_plugin_config_problems_from_file(
        cls, err: ValidationError, base_path: Path
    ) -> Optional[str]:
        cfg_files = _find_config_yaml_files(base_path)
        for cfg_file in cfg_files:
            if problems := _get_problem_with_config(err.errors(), cfg_file):
                return problems

        return None

    @only_raise_attribute_error
    def __getattr__(self, attr_name: str) -> Any:
        _assert_not_ipython_check(attr_name)

        # Allow hyphens in plugin config files.
        attr_name = attr_name.replace("-", "_")
        extra = self.__pydantic_extra__ or {}
        if attr_name in extra:
            return extra[attr_name]

        return super().__getattribute__(attr_name)

    def __getitem__(self, item: str) -> Any:
        extra = self.__pydantic_extra__ or {}
        if item in self.__dict__:
            return self.__dict__[item]

        elif item in extra:
            return extra[item]

        raise KeyError(f"'{item}' not in config.")

    def __contains__(self, key: str) -> bool:
        return key in self.__dict__ or key in (self.__pydantic_extra__ or {})

    def __str__(self) -> str:
        data = self.model_dump(
            mode="json",
            by_alias=True,
            exclude_none=True,
            exclude_unset=True,
            exclude_defaults=True,
        )
        return yaml.safe_dump(data)

    def get(self, key: str, default: Optional[ConfigItemType] = None) -> ConfigItemType:
        extra: dict = self.__pydantic_extra__ or {}
        return self.__dict__.get(key, extra.get(key, default))


class GenericConfig(ConfigDict):
    """
    The default class used when no specialized class is used.
    """


class DeploymentConfig(PluginConfig):
    """
    Add 'deployments' to your config.
    """

    address: AddressType
    """
    The address of the deployment.
    """

    contract_type: str
    """
    The contract type name reference
    (must be a contract in the project).
    """


def _get_problem_with_config(errors: list, path: Path) -> Optional[str]:
    # Attempt to find line numbers in the config matching.
    cfg_content = Source(content=path.read_text(encoding="utf8")).content
    if not cfg_content:
        # Likely won't happen?
        return None

    err_map: dict = {}
    for error in errors:
        if not (location := error.get("loc")):
            continue

        lineno = None
        loc_idx = 0
        depth = len(location)
        list_counter = 0
        for no, line in cfg_content.items():
            loc = location[loc_idx]
            clean_line = line.lstrip()

            if isinstance(loc, int):
                if not clean_line.startswith("- "):
                    # Not a list item.
                    continue

                elif list_counter != loc:
                    # Still search for index.
                    list_counter += 1
                    continue

                # If we get here, we have found the index.
                list_counter = 0

            elif not clean_line.startswith(f"{loc}:"):
                continue

            # Look for the next location up the tree.
            loc_idx += 1

            # Even if we don't find the full path for some reason
            # (perhaps it's missing), we still have the last lineno noticed.
            lineno = no

            if loc_idx < depth:
                continue

            # Found.
            break

        if lineno is not None:
            err_map[lineno] = error
        # else: we looped through the whole file and didn't find anything.

    if not err_map:
        # raise ValidationError as-is (no line numbers found for some reason).
        return None

    error_strs: list[str] = []
    for line_no, cfg_err in err_map.items():
        sub_message = cfg_err.get("msg", cfg_err)
        line_before = line_no - 1 if line_no > 1 else None
        line_after = line_no + 1 if line_no < len(cfg_content) else None
        lines = []
        if line_before is not None:
            lines.append(f"   {line_before}: {cfg_content[line_before]}")
        lines.append(f"-->{line_no}: {cfg_content[line_no]}")
        if line_after is not None:
            lines.append(f"   {line_after}: {cfg_content[line_after]}")

        file_preview = "\n".join(lines)
        sub_message = f"{sub_message}\n{file_preview}\n"
        error_strs.append(sub_message)

    # NOTE: Using reversed because later pydantic errors
    #   appear earlier in the list.
    final_msg = "\n".join(reversed(error_strs)).strip()
    return f"'{clean_path(path)}' is invalid!\n{final_msg}"


class ApeConfig(ExtraAttributesMixin, BaseSettings, ManagerAccessMixin):
    """
    The top-level config.
    """

    def __init__(self, *args, **kwargs):
        project_path = kwargs.get("project")
        super(BaseSettings, self).__init__(*args, **kwargs)
        # NOTE: Cannot reference `self` at all until after super init.
        self._project_path = project_path

    contracts_folder: Optional[str] = None
    """
    The path to the folder containing the contract source files.
    **NOTE**: Non-absolute paths are relative to the project-root.
    If not set, defaults to deducing the contracts folder.
    When deducing, Ape first tries ``"contracts"``, but if
    that folder does not exist, Ape tries to find a folder with
    contracts.
    """

    default_ecosystem: str = "ethereum"
    """
    The default ecosystem to use in Ape.
    """

    dependencies: list[dict] = []
    """
    Project dependency declarations.
    Note: The actual dependency classes are decoded later.
    """

    deployment_data: dict[str, dict[str, list[DeploymentConfig]]] = Field(
        default_factory=dict, alias="deployments"
    )
    """
    Data for deployed contracts from the project.
    """

    interfaces_folder: str = "interfaces"
    """
    The path to the project's interfaces.
    """

    meta: PackageMeta = PackageMeta()
    """
    Metadata about the active project as per EIP
    https://eips.ethereum.org/EIPS/eip-2678#the-package-meta-object
    """

    name: str = ""
    """
    The name of the project.
    """

    base_path: Optional[str] = None
    """
    Use this when the project's base-path is not the
    root of the project.
    """

    request_headers: dict = {}
    """
    Extra request headers for all HTTP requests.
    """

    version: str = ""
    """
    The version of the project.
    """

    # NOTE: Plugin configs are technically "extras".
    model_config = SettingsConfigDict(extra="allow")

    @model_validator(mode="before")
    @classmethod
    def validate_model(cls, model):
        model = model or {}
        fixed_model: dict = {}
        for key, val in model.items():
            # Allows hyphens to work anywhere where underscores are.
            fixed_model[key.replace("-", "_")] = val

        if project := fixed_model.pop("project", None):
            # Resolve local dependencies so relative paths don't cause
            # problems when moving the project around (as happens in local
            # dependencies).
            fixed_deps = []
            dependencies_list = fixed_model.get("dependencies", [])
            if not isinstance(dependencies_list, Iterable):
                raise ConfigError(
                    "Expecting dependencies: to be iterable. "
                    f"Received: {type(dependencies_list).__name__}"
                )

            for dep in fixed_model.get("dependencies", []):
                if not isinstance(dep, dict):
                    raise ConfigError(
                        f"Expecting mapping for dependency. Received: {type(dep).__name__}."
                    )

                fixed_dep = {**dep}
                if "project" not in fixed_dep:
                    fixed_dep["project"] = project
                # else: we might be told to use a different project.
                #   when decoding dependencies, the project is mostly used for
                #  stuff like resolving paths. If this is already set,
                #  this is likely a dependency of a dependency.

                fixed_deps.append(fixed_dep)

            if fixed_deps:
                fixed_model["dependencies"] = fixed_deps

        # field: contracts_folder: Handle if given Path object.
        if "contracts_folder" in fixed_model and isinstance(fixed_model["contracts_folder"], Path):
            fixed_model["contracts_folder"] = str(fixed_model["contracts_folder"])

        return fixed_model

    @cached_property
    def deployments(self) -> dict[str, dict[str, list[DeploymentConfig]]]:
        # Lazily validated.
        for ecosystem_name, ecosystem_deploys in self.deployment_data.items():
            if ecosystem_name not in self.network_manager.ecosystems:
                raise ConfigError(f"Invalid ecosystem '{ecosystem_name}' in deployments config.")

            ecosystem = self.network_manager.ecosystems[ecosystem_name]
            for network_name, network_deploys in ecosystem_deploys.items():
                if network_name not in ecosystem.networks:
                    raise ConfigError(
                        f"Invalid network '{ecosystem_name}:{network_name}' in deployments config."
                    )

        return self.deployment_data

    def __ape_extra_attributes__(self) -> Iterator[ExtraModelAttributes]:
        # This allows `config.my_plugin` to work.
        yield ExtraModelAttributes(
            name="plugin_configs",
            attributes=lambda n: self.get_config(n.replace("-", "_")),
            include_getitem=True,
        )

    @classmethod
    def validate_file(cls, path: Path, **overrides) -> "ApeConfig":
        """
        Create an ApeConfig class using the given path.
        Supports both pyproject.toml and ape-config.[.yml|.yaml|.json] files.

        Raises:
            :class:`~ape.exceptions.ConfigError`: When given an unknown file type
              or the data is invalid.

        Args:
            path (Path): The path to the file.
            **overrides: Config overrides.

        Returns:
            :class:`~ape.api.config.ApeConfig`
        """
        data = {**load_config(path), **overrides}

        # NOTE: We are including the project path here to assist
        #  in relative-path resolution, such as for local dependencies.
        #  You can use relative paths in local dependencies in your
        #  ape-config.yaml file but Ape needs to know the source to be
        #  relative from.
        data["project"] = path.parent

        try:
            return cls.model_validate(data)
        except ValidationError as err:
            if path.suffix == ".json":
                # TODO: Support JSON configs here.
                raise  # The validation error as-is

            if final_msg := _get_problem_with_config(err.errors(), path):
                raise ConfigError(final_msg)
            else:
                raise ConfigError(str(err)) from err

    @classmethod
    def from_manifest(cls, manifest: PackageManifest, **overrides) -> "ApeConfig":
        return cls.model_validate(
            {
                **_get_compile_configs_from_manifest(manifest),
                **_get_dependency_configs_from_manifest(manifest),
                **overrides,
            }
        )

    @property
    def _plugin_configs(self) -> dict:
        # NOTE: Ensure a dict exists so we can add to it
        #  and have it persist.
        self.__pydantic_extra__ = self.__pydantic_extra__ or {}
        return self.__pydantic_extra__

    def __repr__(self) -> str:
        return "<ape-config.yaml>"

    def __str__(self) -> str:
        data = self.model_dump(
            mode="json",
            by_alias=True,
            exclude_none=True,
            exclude_unset=True,
            exclude_defaults=True,
        )
        return yaml.dump(data)

    @only_raise_attribute_error
    def __getattr__(self, attr_name: str) -> Any:
        return get_attribute_with_extras(self, attr_name)

    def __getitem__(self, name: str) -> Any:
        return self.__getattr__(name)

    def __contains__(self, item):
        # Always return True o handle lazy loading plugins.
        return True

    def model_dump(self, *args, **kwargs):
        res = super().model_dump(*args, **kwargs)
        # TODO: For some reason underscore prefixed kwargs
        #  still show up even though Pydantic says they
        #  shouldn't. Figure out why.
        return {k: v for k, v in res.items() if not k.startswith("_")}

    def get(self, name: str) -> Optional[Any]:
        return self.__getattr__(name)

    def get_config(self, plugin_name: str) -> PluginConfig:
        name = plugin_name.replace("-", "_")
        return (
            self.get_plugin_config(name)
            or self.get_custom_ecosystem_config(name)
            or self.get_unknown_config(name)
        )

    def get_plugin_config(self, name: str) -> Optional[PluginConfig]:
        name = name.replace("-", "_")
        cfg = self._plugin_configs.get(name, {})
        if cfg and not isinstance(cfg, dict):
            # Already decoded.
            return cfg

        for plugin_name, config_class in self._get_config_plugin_classes():
            cls: type[PluginConfig] = config_class  # type: ignore
            if plugin_name.replace("-", "_") != name:
                continue

            if cls != ConfigDict:
                # NOTE: Will raise if improperly provided keys
                config = cls.from_overrides(
                    cfg, plugin_name=plugin_name, project_path=self._project_path
                )
            else:
                # NOTE: Just use it directly as a dict if `ConfigDict` is passed
                config = cfg

            self._plugin_configs[name] = config
            return config

        return None

    def _get_config_plugin_classes(self):
        # NOTE: Abstracted for easily mocking in tests.
        return self.plugin_manager.config_class

    def get_custom_ecosystem_config(self, name: str) -> Optional[PluginConfig]:
        name = name.replace("-", "_")
        if not (networks := self.get_plugin_config("networks")):
            # Shouldn't happen.
            return None

        for network in networks.custom:
            if name not in (network.ecosystem, network.ecosystem.replace("-", "_")):
                continue

            # Check if has a cached override.
            override = self._plugin_configs.get(name, {})
            if not isinstance(override, dict):
                return override

            # Custom network found.
            from ape_ethereum import EthereumConfig

            ethereum = cast(EthereumConfig, self.get_plugin_config("ethereum"))
            return ethereum.from_overrides(
                override, plugin_name=name, project_path=self._project_path
            )

        return None

    def get_unknown_config(self, name: str) -> PluginConfig:
        # This happens when a plugin is not installed but still configured.
        result = (self.__pydantic_extra__ or {}).get(name, PluginConfig())
        if isinstance(result, dict):
            return PluginConfig.from_overrides(
                result, plugin_name=name, project_path=self._project_path
            )

        return result

    def write_to_disk(self, destination: Path, replace: bool = False):
        """
        Write this config to a file.

        Args:
            destination (Path): The path to write to.
            replace (bool): Set to ``True`` to overwrite the file if it exists.
        """
        if destination.exists() and not replace:
            raise ValueError(f"Destination {destination} exists.")
        elif replace:
            destination.unlink(missing_ok=True)

        if destination.suffix in (".yml", ".yaml"):
            destination.parent.mkdir(parents=True, exist_ok=True)
            with open(destination, "x") as file:
                data = self.model_dump(by_alias=True, mode="json")
                yaml.safe_dump(data, file)

        elif destination.suffix == ".json":
            destination.write_text(self.model_dump_json(by_alias=True), encoding="utf8")

        else:
            raise ConfigError(f"Unsupported destination file type '{destination}'.")


def _get_compile_configs_from_manifest(manifest: PackageManifest) -> dict[str, dict]:
    configs: dict[str, dict] = {}
    for compiler in [x for x in manifest.compilers or [] if x.settings]:
        name = compiler.name.strip().lower()
        compiler_data = {}
        settings = compiler.settings or {}
        remapping_list = []
        for remapping in settings.get("remappings") or []:
            parts = remapping.split("=")
            key = parts[0]
            link = parts[1]
            if link.startswith(f".cache{os.path.sep}"):
                link = os.path.sep.join(link.split(f".cache{os.path.sep}"))[1:]

            new_entry = f"{key}={link}"
            remapping_list.append(new_entry)

        if remapping_list:
            compiler_data["import_remapping"] = remapping_list

        if "evm_version" in settings:
            compiler_data["evm_version"] = settings["evm_version"]

        if compiler_data:
            configs[name] = compiler_data

    return configs


def _get_dependency_configs_from_manifest(manifest: PackageManifest) -> dict:
    dependencies_config: list[dict] = []
    dependencies = manifest.dependencies or {}
    for package_name, uri in dependencies.items():
        if "://" not in str(uri) and hasattr(uri, "scheme"):
            uri_str = f"{uri.scheme}://{uri}"
        else:
            uri_str = str(uri)

        dependency: dict = {"name": str(package_name)}
        if uri_str.startswith("https://github.com/") and "releases/tag" in uri_str:
            # 'https:', '', 'github.com', org, repo, 'releases', 'tag', version
            # Fails with ValueError if not matching
            try:
                _, _, _, org, repo, _, _, version = uri_str.split("/")
            except ValueError:
                raise ConfigError("")

            dependency["github"] = f"{org}/{repo}"

            # If version fails, the dependency system will automatically try `ref`.
            dependency["version"] = version

        elif uri_str.startswith("file://"):
            dependency["local"] = uri_str.replace("file://", "")

        else:
            logger.error(f"Manifest URI {uri_str} not a supported dependency.")
            continue

        dependencies_config.append(dependency)

    return {"dependencies": dependencies_config} if dependencies_config else {}
