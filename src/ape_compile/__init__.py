from pathlib import Path
from typing import List, Optional

from pydantic import field_validator

from ape import plugins
from ape.api import PluginConfig


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

    """
    Source exclusion globs across all file types.
    """
    exclude: List[str] = []

    cache_folder: Optional[Path] = None
    """
    Path to contract dependency cache directory (e.g. `contracts/.cache`)
    """

    @property
    def base_path(self) -> Path:
        """The base directory for compilation file path references"""

        # These should be initialized by plugin config loading and pydantic validators before the
        # time this prop is accessed.
        assert self._config_manager is not None
        assert self.cache_folder is not None

        # If the dependency cache folder is configured, to be outside of the contracts dir, we want
        # to use the projects folder to be the base dir for copmilation.
        if self._config_manager.contracts_folder not in self.cache_folder.parents:
            return self._config_manager.PROJECT_FOLDER

        # Otherwise, we're defaulting to contracts folder for backwards compatibility. Changing this
        # will cause existing projects to compile to different bytecode.
        return self._config_manager.contracts_folder

    @field_validator("exclude", mode="before")
    @classmethod
    def validate_exclude(cls, value):
        return value or []


@plugins.register(plugins.Config)
def config_class():
    return Config
