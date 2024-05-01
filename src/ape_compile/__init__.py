from pathlib import Path
from typing import Optional, Set

from pydantic import field_validator, model_validator

from ape import plugins
from ape.api import PluginConfig
from ape.utils.misc import SOURCE_EXCLUDE_PATTERNS

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

    exclude: Set[str] = set()
    """
    Source exclusion globs across all file types.
    """

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
        # to use the projects folder to be the base dir for compilation.
        if self._config_manager.contracts_folder not in self.cache_folder.parents:
            return self._config_manager.PROJECT_FOLDER

        # Otherwise, we're defaulting to contracts folder for backwards compatibility. Changing this
        # will cause existing projects to compile to different bytecode.
        return self._config_manager.contracts_folder

    @model_validator(mode="after")
    def validate_cache_folder(self):
        if self._config_manager is None:
            return  # Not enough information to continue at this time

        contracts_folder = self._config_manager.contracts_folder
        project_folder = self._config_manager.PROJECT_FOLDER

        # Set unconfigured default
        if self.cache_folder is None:
            self.cache_folder = contracts_folder / DEFAULT_CACHE_FOLDER_NAME

        # If we get a relative path, assume it's relative to project root (where the config file
        # lives)
        elif not self.cache_folder.is_absolute():
            self.cache_folder = project_folder / self.cache_folder

        # Do not allow escape of the project folder for security and functionality reasons. Paths
        # outside the relative compilation root are not portable and will cause bytecode changes.
        project_resolved = project_folder.resolve()
        cache_resolved = self.cache_folder.resolve()
        if project_resolved not in cache_resolved.parents:
            raise ValueError(
                "cache_folder must be a child of the project directory. "
                f"{project_resolved} not in {cache_resolved}"
            )

    @field_validator("exclude", mode="before")
    @classmethod
    def validate_exclude(cls, value):
        return {*(value or []), *SOURCE_EXCLUDE_PATTERNS}


@plugins.register(plugins.Config)
def config_class():
    return Config
