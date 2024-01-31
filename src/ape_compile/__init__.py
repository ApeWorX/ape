from pathlib import Path
from typing import List, Optional

from pydantic import field_validator, model_validator

from ape import plugins
from ape.api import PluginConfig

DEFAULT_CACHE_FOLDER_NAME = ".cache"  # default relative to contracts/


class Config(PluginConfig):
    include_dependencies: bool = False
    """
    Set to ``True`` to compile dependencies during ``ape compile``.
    Generally, dependencies are not compiled during ``ape compile``
    This is because dependencies may not compile in Ape on their own,
    but you can still reference them in your project's contracts' imports.
    Some projects may be more dependency-based and wish to have the
    contract types always compiled during ``ape compile``, and these projects
    should configure ``include_dependencies`` to be ``True``.
    """

    exclude: List[str] = ["*package.json", "*package-lock.json", "*tsconfig.json"]
    """
    Source exclusion globs across all file types.
    """

    cache_folder: Optional[Path] = None
    """
    Path to contract dependency cache directory (e.g. `contracts/.cache`)
    """

    @model_validator(mode="after")
    def validate_cache_folder(self):
        if self._config_manager is None:
            return  # Not enough information to continue at this time

        # Handle setting default
        if self.cache_folder is None:
            contracts_folder = self._config_manager.contracts_folder
            self.cache_folder = contracts_folder / DEFAULT_CACHE_FOLDER_NAME
        elif not self.cache_folder.is_absolute():
            self.cache_folder = self.cache_folder.expanduser().resolve()

    @field_validator("exclude", mode="before")
    @classmethod
    def validate_exclude(cls, value):
        return value or []


@plugins.register(plugins.Config)
def config_class():
    return Config
