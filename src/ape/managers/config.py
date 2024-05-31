import os
from functools import cached_property
from pathlib import Path
from typing import Any, Optional

from ethpm_types import PackageManifest

from ape.api import PluginConfig
from ape.api.config import ApeConfig
from ape.managers.base import BaseManager
from ape.utils import log_instead_of_fail
from ape.utils.basemodel import (
    ExtraAttributesMixin,
    ExtraModelAttributes,
    get_attribute_with_extras,
    get_item_with_extras,
    only_raise_attribute_error,
)

CONFIG_FILE_NAME = "ape-config.yaml"


class ConfigManager(ExtraAttributesMixin, BaseManager):
    """
    An Ape configuration manager, controlled by ``ape-config.yaml``
    files. **NOTE**: This is a singleton wrapper class that
    points to the local project's config. For the config field
    definitions, see :class:`~ape.api.config.ApeConfig`.
    """

    def __init__(self, data_folder: Optional[Path] = None, request_header: Optional[dict] = None):
        if not data_folder and "APE_DATA_FOLDER" in os.environ:
            self.DATA_FOLDER = Path(os.environ["APE_DATA_FOLDER"])
        else:
            self.DATA_FOLDER = data_folder or Path.home() / ".ape"

        self.REQUEST_HEADER = request_header or {}

    def __ape_extra_attributes__(self):
        # The "extra" attributes are the local project's
        # config attributes. To see the actual ``ape-config.yaml``
        # definitions, see :class:`~ape.api.config.ApeConfig`.
        yield ExtraModelAttributes(
            name="config",
            # Active project's config.
            attributes=self.local_project.config,
            include_getitem=True,
        )

    @log_instead_of_fail(default="<ConfigManager>")
    def __repr__(self) -> str:
        return f"<{CONFIG_FILE_NAME}>"

    def __str__(self) -> str:
        return str(self.local_project.config)

    @only_raise_attribute_error
    def __getattr__(self, name: str) -> Any:
        """
        The root config manager (funneling to this method)
        refers to the local project's config. Config is loaded
        per project in Ape to support multi-project environments
        and a smarter dependency system.

        See :class:`~ape.api.config.ApeConfig` for field definitions
        and model-related controls.
        """

        return get_attribute_with_extras(self, name)

    def __getitem__(self, name: str) -> Any:
        return get_item_with_extras(self, name)

    @cached_property
    def global_config(self) -> ApeConfig:
        """
        Root-level configurations, loaded from the
        data folder. **NOTE**: This only needs to load
        once and applies to all projects.
        """
        return self.load_global_config()

    def load_global_config(self) -> ApeConfig:
        path = self.DATA_FOLDER / CONFIG_FILE_NAME
        return ApeConfig.validate_file(path) if path.is_file() else ApeConfig.model_validate({})

    def merge_with_global(self, project_config: ApeConfig) -> ApeConfig:
        global_data = self.global_config.model_dump(by_alias=True)
        project_data = project_config.model_dump(by_alias=True)
        merged_data = merge_configs(global_data, project_data)
        return ApeConfig.model_validate(merged_data)

    @classmethod
    def extract_config(cls, manifest: PackageManifest, **overrides) -> ApeConfig:
        """
        Calculate the ape-config data from a package manifest.

        Args:
            manifest (PackageManifest): The manifest.
            **overrides: Custom config settings.

        Returns:
            :class:`~ape.managers.config.ApeConfig`: Config data.
        """
        return ApeConfig.from_manifest(manifest, **overrides)

    def get_config(self, plugin_name: str) -> PluginConfig:
        """
        Get the config for a plugin.

        Args:
            plugin_name (str): The name of the plugin.

        Returns:
            :class:`~ape.api.config.PluginConfig`
        """
        try:
            return self.__getattr__(plugin_name)
        except AttributeError:
            # Empty config.
            return PluginConfig()


def merge_configs(*cfgs: dict) -> dict:
    if len(cfgs) == 0:
        return {}
    elif len(cfgs) == 1:
        return cfgs[0]

    new_base = _merge_configs(cfgs[0], cfgs[1])
    return merge_configs(new_base, *cfgs[2:])


def _merge_configs(base: dict, secondary: dict) -> dict:
    result: dict = {}

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
