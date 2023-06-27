import json
import os
import tempfile
from pathlib import Path
from typing import Dict, Iterable, Optional, Type

from ethpm_types import PackageManifest
from ethpm_types.utils import AnyUrl
from pydantic import FileUrl, HttpUrl, root_validator
from semantic_version import NpmSpec, Version  # type: ignore

from ape.api import DependencyAPI
from ape.exceptions import ProjectError, UnknownVersionError
from ape.logging import logger
from ape.utils import ManagerAccessMixin, cached_property, github_client, load_config


class DependencyManager(ManagerAccessMixin):
    DATA_FOLDER: Path

    def __init__(self, data_folder: Path):
        self.DATA_FOLDER = data_folder

    @cached_property
    def dependency_types(self) -> Dict[str, Type[DependencyAPI]]:
        dependency_classes: Dict[str, Type[DependencyAPI]] = {
            "github": GithubDependency,
            "local": LocalDependency,
            "npm": NpmDependency,
        }

        for _, (config_key, dependency_class) in self.plugin_manager.dependencies:
            assert issubclass(dependency_class, DependencyAPI)  # For mypy
            dependency_classes[config_key] = dependency_class

        return dependency_classes

    def decode_dependency(self, config_dependency_data: Dict) -> DependencyAPI:
        for key, dependency_cls in self.dependency_types.items():
            if key in config_dependency_data:
                return dependency_cls(**config_dependency_data)

        dep_id = config_dependency_data.get("name", json.dumps(config_dependency_data))
        raise ProjectError(f"No installed dependency API that supports '{dep_id}'.")


class GithubDependency(DependencyAPI):
    """
    A dependency from Github. Use the ``github`` key in your ``dependencies:``
    section of your ``ape-config.yaml`` file to declare a dependency from GitHub.

    Config example::

        dependencies:
          - name: OpenZeppelin
            github: OpenZeppelin/openzeppelin-contracts
            version: 4.4.0
    """

    github: str
    """
    The Github repo ID e.g. the organization name followed by the repo name,
    such as ``dapphub/erc20``.
    """

    # TODO: Remove at >= 0.7
    branch: Optional[str] = None
    """
    **DEPRECATED**: Use ``ref:``.
    """

    ref: Optional[str] = None
    """
    The branch or tag to use.

    **NOTE**: Will be ignored if given a version.
    """

    @cached_property
    def _reference(self) -> Optional[str]:
        if self.ref:
            return self.ref

        elif self.branch:
            logger.warning("'branch:' config is deprecated. Use 'ref:' instead.")
            return self.branch

        return None

    @cached_property
    def version_id(self) -> str:
        if self._reference:
            return self._reference

        elif self.version and self.version != "latest":
            return self.version

        latest_release = github_client.get_release(self.github, "latest")
        return latest_release.tag_name

    @property
    def uri(self) -> AnyUrl:
        _uri = f"https://github.com/{self.github.strip('/')}"
        if self.version:
            version = f"v{self.version}" if not self.version.startswith("v") else self.version
            _uri = f"{_uri}/releases/tag/{version}"
        elif self._reference:
            _uri = f"{_uri}/tree/{self._reference}"

        return HttpUrl(_uri, scheme="https")

    def __repr__(self):
        return f"<{self.__class__.__name__} github={self.github}>"

    def extract_manifest(self, use_cache: bool = True) -> PackageManifest:
        if use_cache and self.cached_manifest:
            # Already downloaded
            return self.cached_manifest

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_project_path = (Path(temp_dir) / self.name).resolve()
            temp_project_path.mkdir(exist_ok=True, parents=True)

            if self._reference:
                github_client.clone_repo(self.github, temp_project_path, branch=self._reference)

            else:
                try:
                    github_client.download_package(
                        self.github, self.version or "latest", temp_project_path
                    )
                except UnknownVersionError as err:
                    logger.warning(
                        f"No official release found for version '{self.version}'. "
                        "Use `ref:` instead of `version:` for release tags. "
                        "Checking for matching tags..."
                    )
                    try:
                        github_client.clone_repo(
                            self.github, temp_project_path, branch=self.version
                        )
                    except Exception:
                        # Raise the UnknownVersionError.
                        raise err

            return self._extract_local_manifest(temp_project_path, use_cache=use_cache)


class LocalDependency(DependencyAPI):
    """
    A dependency that is already downloaded on the local machine.

    Config example::

        dependencies:
          - name: Dependency
            local: path/to/dependency
    """

    local: str
    version = "local"

    @root_validator()
    def validate_contracts_folder(cls, value):
        if value.get("contracts_folder") not in (None, "contracts"):
            return value

        # If using default value, check if exists
        local_path_value = value.get("local") or os.getcwd()
        local_project_path = Path(local_path_value)
        try_contracts_path = local_project_path / "contracts"
        if try_contracts_path.is_dir():
            return value

        # Attempt to read value from config
        config_file = local_project_path / "ape-config.yaml"
        if config_file.is_file():
            config_data = load_config(config_file)
            if "contracts_folder" in config_data:
                value["contracts_folder"] = config_data["contracts_folder"]

        return value

    @property
    def path(self) -> Path:
        given_path = Path(self.local).resolve().absolute()
        if not given_path.is_dir():
            raise ProjectError(f"No project exists at path '{given_path}'.")

        return given_path

    @property
    def version_id(self) -> str:
        return self.version

    @property
    def uri(self) -> AnyUrl:
        path = self._target_manifest_cache_file.resolve().absolute()
        return FileUrl(f"file://{path}", scheme="file")

    def extract_manifest(self, use_cache: bool = True) -> PackageManifest:
        return self._extract_local_manifest(self.path, use_cache=use_cache)


class NpmDependency(DependencyAPI):
    """
    A dependency from the Node Package Manager (NPM).

    Config example::

        dependencies:
          - name: safe-singleton-factory
            npm: "@gnosis.pm/safe-singleton-factory"
            version: 1.0.14
    """

    npm: str
    """
    The NPM repo ID e.g. the organization name followed by the repo name,
    such as ``"@gnosis.pm/safe-singleton-factory"``.
    """

    @cached_property
    def version_id(self) -> str:
        version_from_config = self.version
        version_from_json = self.version_from_json
        version_from_local_json = self.version_from_local_json
        if version_from_config:
            for other_version in (version_from_json, version_from_local_json):
                if not other_version:
                    continue

                semver = NpmSpec(other_version)
                if other_version and not semver.match(Version(version_from_config)):
                    raise ProjectError(
                        f"Version mismatch for {self.npm}. Is {self.version} in ape config "
                        f"but {other_version} in package.json. "
                        f"Try aligning versions and/or running `npm install`."
                    )

        if version_from_config:
            return version_from_config
        elif version_from_json:
            return version_from_json
        elif version_from_local_json:
            return version_from_local_json
        else:
            raise ProjectError(
                f"Missing version for NPM dependency '{self.name}'. " "Have you run `npm install`?"
            )

    @property
    def package_folder(self) -> Path:
        return Path.cwd() / "node_modules" / str(self.npm)

    @cached_property
    def version_from_json(self) -> Optional[str]:
        """
        The version from package.json in the installed package.
        Requires having run `npm install`.
        """
        return _get_version_from_package_json(self.package_folder)

    @cached_property
    def version_from_local_json(self) -> Optional[str]:
        """
        The version from your project's package.json, if exists.
        """
        return _get_version_from_package_json(
            self.project_manager.path, path=("dependencies", self.npm)
        )

    @property
    def uri(self) -> AnyUrl:
        _uri = f"https://www.npmjs.com/package/{self.npm}/v/{self.version}"
        return HttpUrl(_uri, scheme="https")

    def extract_manifest(self, use_cache: bool = True) -> PackageManifest:
        if use_cache and self.cached_manifest:
            # Already downloaded
            return self.cached_manifest

        if self.package_folder.is_dir():
            if (
                self.version
                and self.version_from_json
                and self.version not in self.version_from_json
            ):
                raise ProjectError(
                    f"Version mismatch for {self.npm}. Is {self.version} in ape config"
                    f"but {self.version_from_json} in package.json."
                )

            return self._extract_local_manifest(self.package_folder, use_cache=use_cache)

        else:
            raise ProjectError(f"NPM package '{self.npm}' not installed.")


def _get_version_from_package_json(
    base_path: Path, path: Optional[Iterable[str]] = None
) -> Optional[str]:
    package_json = base_path / "package.json"
    if not package_json.is_file():
        return None

    try:
        data = json.loads(package_json.read_text())
    except Exception as err:
        logger.warning(f"Failed to parse package.json: {err}")
        return None

    for key in path or []:
        if key not in data:
            return None

        data = data[key]

    if isinstance(data, str):
        return data

    elif not isinstance(data, dict):
        return None

    return data.get("version")
