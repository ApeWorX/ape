import json
import os
import shutil
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Type

from ethpm_types import PackageManifest
from packaging.version import Version
from pydantic import AnyUrl, FileUrl, HttpUrl, model_validator

from ape.api import DependencyAPI
from ape.exceptions import ProjectError, UnknownVersionError
from ape.logging import logger
from ape.utils import (
    ManagerAccessMixin,
    cached_property,
    github_client,
    load_config,
    log_instead_of_fail,
    pragma_str_to_specifier_set,
    run_in_tempdir,
)


class DependencyManager(ManagerAccessMixin):
    DATA_FOLDER: Path
    _cached_dependencies: Dict[str, Dict[str, Dict[str, DependencyAPI]]] = {}

    def __init__(self, data_folder: Path):
        self.DATA_FOLDER = data_folder

    @property
    def packages_folder(self) -> Path:
        return self.DATA_FOLDER / "packages"

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

    def load_dependencies(
        self, project_id: str, use_cache: bool = True
    ) -> Dict[str, Dict[str, DependencyAPI]]:
        if use_cache and project_id in self._cached_dependencies:
            return self._cached_dependencies[project_id]

        for dependency_config in self.config_manager.dependencies:
            dependency_name = dependency_config.name
            version_id = dependency_config.version_id
            project_dependencies = self._cached_dependencies.get(project_id, {})

            if (
                use_cache
                and dependency_name in project_dependencies
                and version_id in project_dependencies[dependency_name]
            ):
                # Already cached
                continue

            # Cache manifest for next time.
            if dependency_name in project_dependencies:
                # Dependency is cached but version is not.
                project_dependencies[dependency_name][version_id] = dependency_config
            else:
                # First time caching dependency
                project_dependencies[dependency_name] = {version_id: dependency_config}

            self._cached_dependencies[project_id] = project_dependencies

            # Only extract manifest if wasn't cached and must happen after caching.
            dependency_config.extract_manifest(use_cache=use_cache)

        return self._cached_dependencies.get(project_id, {})

    def get_versions(self, name: str) -> List[Path]:
        path = self.packages_folder / name
        if not path.is_dir():
            logger.warning("Dependency not installed.")
            return []

        return [x for x in path.iterdir() if x.is_dir()]

    def remove_dependency(self, project_id: str, name: str, versions: Optional[List[str]] = None):
        self._remove_local_dependency(project_id, name, versions=versions)
        self._remove_disk_dependency(name, versions=versions)

    def _remove_disk_dependency(self, name: str, versions: Optional[List[str]] = None):
        versions = versions or []
        available_versions = self.get_versions(name)
        if not available_versions:
            # Clean up (user was already warned).
            if (self.packages_folder / name).is_dir():
                shutil.rmtree(self.packages_folder / name, ignore_errors=True)

            return

        # Use single version if there is one and wasn't given anything.
        versions = (
            [x.name for x in available_versions]
            if not versions and len(available_versions) == 1
            else versions
        )
        if not versions:
            raise ProjectError("Please specify versions to remove.")

        path = self.packages_folder / name
        for version in versions:
            if (path / version).is_dir():
                version_key = version
            elif (path / f"v{version}").is_dir():
                version_key = f"v{version}"
            else:
                raise ProjectError(f"Version '{version}' of package '{name}' is not installed.")

            path = self.packages_folder / name / version_key
            if not path.is_dir():
                available_versions_str = ", ".join([x.name for x in available_versions])
                raise ProjectError(
                    f"Version '{version}' not found in dependency {name}. "
                    f"Available versions: {available_versions_str}"
                )

            shutil.rmtree(path)

        # If there are no more versions, delete the whole package directory.
        remaining_versions = self.get_versions(name)
        if not remaining_versions:
            shutil.rmtree(self.packages_folder / name, ignore_errors=True)

    def _remove_local_dependency(
        self, project_id: str, name: str, versions: Optional[List[str]] = None
    ):
        versions = versions or []
        if name in self._cached_dependencies.get(project_id, {}):
            versions_available = self.dependency_manager.get_versions(name)
            if not versions and len(versions_available) == 1:
                versions = [x.name for x in versions_available]
            elif not versions:
                raise ProjectError("`versions` kwarg required.")

            local_versions = self._cached_dependencies.get(project_id, {}).get(name, {})
            for version in versions:
                if version in local_versions:
                    version_key = version
                elif f"v{version}" in local_versions:
                    version_key = f"v{version}"
                else:
                    logger.warning(f"Version '{version}' not installed.")
                    continue

                del self._cached_dependencies[project_id][name][version_key]

        # Local clean ups.
        if (
            project_id in self._cached_dependencies
            and name in self._cached_dependencies[project_id]
            and not self._cached_dependencies[project_id][name]
        ):
            del self._cached_dependencies[project_id][name]

        if project_id in self._cached_dependencies and not self._cached_dependencies[project_id]:
            del self._cached_dependencies[project_id]


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

    ref: Optional[str] = None
    """
    The branch or tag to use.

    **NOTE**: Will be ignored if given a version.
    """

    @model_validator(mode="after")
    @classmethod
    def ensure_ref_or_version(cls, dep):
        if dep.ref is None and dep.version is None:
            raise ValueError("GitHub dependency must have either ref or version specified.")

        return dep

    @cached_property
    def version_id(self) -> str:
        if self.ref:
            return self.ref

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
        elif self.ref:
            _uri = f"{_uri}/tree/{self.ref}"

        return HttpUrl(_uri)

    @log_instead_of_fail(default="<GithubDependency>")
    def __repr__(self) -> str:
        cls_name = getattr(type(self), "__name__", GithubDependency.__name__)
        return f"<{cls_name} github={self.github}>"

    def extract_manifest(self, use_cache: bool = True) -> PackageManifest:
        if use_cache and self.cached_manifest:
            # Already downloaded
            return self.cached_manifest

        return run_in_tempdir(lambda p: self._extract_manifest_in_path(p, use_cache=use_cache))

    def _extract_manifest_in_path(self, path: Path, use_cache: bool = True) -> PackageManifest:
        if self.ref:
            github_client.clone_repo(self.github, path, branch=self.ref)

        else:
            try:
                github_client.download_package(self.github, self.version or "latest", path)
            except UnknownVersionError as err:
                logger.warning(
                    f"No official release found for version '{self.version}'. "
                    "Use `ref:` instead of `version:` for release tags. "
                    "Checking for matching tags..."
                )
                try:
                    github_client.clone_repo(self.github, path, branch=self.version)
                except Exception:
                    # Raise the UnknownVersionError.
                    raise err

        return self._extract_local_manifest(path, use_cache=use_cache)


class LocalDependency(DependencyAPI):
    """
    A dependency that is already downloaded on the local machine.

    Config example::

        dependencies:
          - name: Dependency
            local: path/to/dependency
    """

    local: str
    version: str = "local"

    @model_validator(mode="before")
    @classmethod
    def validate_contracts_folder(cls, value):
        if value.get("contracts_folder") not in (None, "contracts"):
            return value

        elif cfg_value := value.get("config_override", {}).get("contracts_folder"):
            value["contracts_folder"] = cfg_value
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
        return Path(self.local).resolve().absolute()

    @property
    def version_id(self) -> str:
        return self.version

    @property
    def uri(self) -> AnyUrl:
        return FileUrl(self.path.as_uri())

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

                if semver := pragma_str_to_specifier_set(other_version):
                    if other_version and not next(
                        semver.filter([Version(version_from_config)]), None
                    ):
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
    def package_suffix(self) -> Path:
        return Path("node_modules") / str(self.npm)

    @property
    def package_folder(self) -> Path:
        return Path.cwd() / self.package_suffix

    @property
    def global_package_folder(self) -> Path:
        return Path.home() / self.package_suffix

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
        return HttpUrl(_uri)

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

        elif self.global_package_folder.is_dir():
            return self._extract_local_manifest(self.global_package_folder, use_cache=use_cache)

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
