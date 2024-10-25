from abc import abstractmethod
from functools import cached_property
from pathlib import Path
from typing import Optional

from pydantic import Field, field_validator

from ape.api.config import ApeConfig
from ape.utils.basemodel import BaseInterfaceModel


class DependencyAPI(BaseInterfaceModel):
    """
    An API for obtaining sources.
    """

    name: str
    """
    The package-name of the dependency.
    """

    config_override: dict = Field(default_factory=dict, repr=False)
    """
    Set different config than what Ape can deduce.
    """

    @property
    @abstractmethod
    def package_id(self) -> str:
        """
        The full name of the package, used for storage.
        Example: ``OpenZeppelin/openzepplin-contracts``.
        """

    @property
    @abstractmethod
    def version_id(self) -> str:
        """
        The ID to use as the sub-directory in the download cache.
        Most often, this is either a version number or a branch name.
        """

    @property
    @abstractmethod
    def uri(self) -> str:
        """
        The URI for the package.
        """

    @abstractmethod
    def fetch(self, destination: Path):
        """
        Fetch the dependency. E.g. for GitHub dependency,
        download the files to the destination.

        Args:
            destination (Path): The destination for the dependency
              files.
        """

    @field_validator("name", mode="before")
    @classmethod
    def validate_name(cls, value):
        return (value or "").lower().replace("_", "-")

    def __hash__(self) -> int:
        return hash(f"{self.package_id}@{self.version_id}")


class ProjectAPI(BaseInterfaceModel):
    """
    An API for recognizing different project types,
    such as brownie projects versus ape projects.
    NOTE: This assumed the project sources are available and unpacked.
    Use :class:`~ape.api.projects.DependencyAPI` to fetch different
    projects. The main task of the project API is to generate
    a configuration needed to compile in Ape.
    """

    path: Path
    """
    The location of the project.
    """

    @property
    @abstractmethod
    def is_valid(self) -> bool:
        """
        Return ``True`` when detecting a project of this type.
        """

    @abstractmethod
    def extract_config(self, **overrides) -> "ApeConfig":
        """
        Extra configuration from the project so that
        Ape understands the dependencies and how to compile everything.

        Args:
            **overrides: Config overrides.

        Returns:
            :class:`~ape.managers.config.ApeConfig`
        """

    @classmethod
    def attempt_validate(cls, **kwargs) -> Optional["ProjectAPI"]:
        try:
            instance = cls(**kwargs)
        except ValueError:
            return None

        return instance if instance.is_valid else None


class ApeProject(ProjectAPI):
    """
    The default ProjectAPI implementation.
    """

    CONFIG_FILE_NAME: str = "ape-config"
    EXTENSIONS: tuple[str, ...] = (".yaml", ".yml", ".json")

    @property
    def is_valid(self) -> bool:
        return True  # If all else fails, treat as a default Ape project.

    @cached_property
    def config_file(self) -> Path:
        if self._using_pyproject_toml:
            return self._pyproject_toml

        # else: check for an ape-config file.
        for ext in self.EXTENSIONS:
            path = self.path / f"{self.CONFIG_FILE_NAME}{ext}"
            if path.is_file():
                return path

        # Default: non-existing ape-config.yaml file.
        return self.path / f"{self.CONFIG_FILE_NAME}.yaml"

    @property
    def _pyproject_toml(self) -> Path:
        return self.path / "pyproject.toml"

    @property
    def _using_pyproject_toml(self) -> bool:
        return self._pyproject_toml.is_file() and "[tool.ape" in self._pyproject_toml.read_text()

    def extract_config(self, **overrides) -> ApeConfig:
        return ApeConfig.validate_file(self.config_file, **overrides)
