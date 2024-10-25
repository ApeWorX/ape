import json
import os
import shutil
from collections.abc import Iterable
from functools import cached_property
from importlib import metadata
from pathlib import Path
from typing import Optional, Union

import requests
from pydantic import model_validator

from ape.api.projects import DependencyAPI
from ape.exceptions import ProjectError
from ape.logging import logger
from ape.managers.project import _version_to_options
from ape.utils._github import _GithubClient, github_client
from ape.utils.basemodel import ManagerAccessMixin
from ape.utils.os import clean_path, extract_archive, get_package_path, in_tempdir


def _fetch_local(src: Path, destination: Path, config_override: Optional[dict] = None):
    if src.is_dir():
        project = ManagerAccessMixin.Project(src, config_override=config_override)
        project.unpack(destination)
    elif src.is_file() and src.suffix == ".json":
        # Using a manifest directly as a dependency.
        if not destination.suffix:
            destination = destination / src.name

        destination.unlink(missing_ok=True)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(src.read_text(), encoding="utf8")


class LocalDependency(DependencyAPI):
    """
    A dependency located on the local machine.
    """

    local: Path
    """
    The root path (and API defining key) to the dependency files.
    """

    version: Optional[str] = None
    """
    Specified version.
    """

    @model_validator(mode="before")
    @classmethod
    def validate_local_path(cls, model):
        # Resolves the relative path so if the dependency API
        # data moves, it will still work.
        path = Path(model["local"])

        # Automatically include `"name"`.
        if "name" not in model:
            model["name"] = path.stem

        if path.is_absolute():
            return model

        elif "project" in model:
            # Just in case relative paths didn't get resolved.
            # Note: Generally, they should be resolved at model
            #  construction time, if parsing a config file normally.
            project = model.pop("project")
            model["local"] = (project / path).resolve()

        return model

    def __repr__(self) -> str:
        path = clean_path(self.local)
        return f"<LocalDependency local={path}, version={self.version}>"

    @property
    def package_id(self) -> str:
        path = self.local
        if in_tempdir(path):
            # Avoids never-ending tmp paths.
            return self.name

        else:
            return self.local.as_posix()

    @property
    def version_id(self) -> str:
        return self.version or "local"

    @property
    def uri(self) -> str:
        return self.local.as_uri()

    def fetch(self, destination: Path):
        if destination.is_dir():
            destination = destination / self.name

        _fetch_local(self.local, destination, config_override=self.config_override)


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
    The branch or tag to use. When using this field
    instead of the 'release' field, the repository
    gets cloned instead of downloaded via the
    official GitHub release API.

    **NOTE**: Will be ignored if given a 'release'.
    """

    version: Optional[str] = None
    """
    The release version to use. When using this
    field instead of the 'ref' field, the GitHub
    release API is used to fetch instead of cloning.

    **NOTE**: Will be ignored if given a 'ref'.
    """

    # Exists as property so can be changed for testing.
    _github_client: _GithubClient = github_client

    @model_validator(mode="before")
    @classmethod
    def _validate_model(cls, model):
        # branch -> ref
        if "branch" in model and "ref" not in model:
            # Handle branch as an alias.
            model["ref"] = model.pop("branch")

        if "name" not in model and "github" in model:
            # Calculate a default name.
            model["name"] = model["github"].split("/")[-1].lower()

        return model

    @model_validator(mode="after")
    @classmethod
    def ensure_ref_or_version(cls, dep):
        if dep.ref is None and dep.version is None:
            raise ValueError("GitHub dependency must have either ref or version specified.")

        return dep

    @property
    def package_id(self) -> str:
        return self.github

    @cached_property
    def version_id(self) -> str:
        if self.ref:
            return self.ref

        elif self.version and self.version != "latest":
            return self.version

        latest_release = self._github_client.get_latest_release(self.org_name, self.repo_name)
        return latest_release["tag_name"]

    @cached_property
    def org_name(self) -> str:
        return self.github.split("/")[0]

    @cached_property
    def repo_name(self) -> str:
        return self.github.split("/")[1]

    @property
    def uri(self) -> str:
        _uri = f"https://github.com/{self.github.strip('/')}"
        if self.version:
            version = f"v{self.version}" if not self.version.startswith("v") else self.version
            _uri = f"{_uri}/releases/tag/{version}"
        elif self.ref:
            _uri = f"{_uri}/tree/{self.ref}"

        return _uri

    def __repr__(self) -> str:
        cls_name = getattr(type(self), "__name__", GithubDependency.__name__)
        return f"<{cls_name} github={self.github}>"

    def fetch(self, destination: Path):
        destination.parent.mkdir(exist_ok=True, parents=True)
        if ref := self.ref:
            # Fetch using git-clone approach (by git-reference).
            # NOTE: destination path does not exist at this point.
            self._fetch_ref(ref, destination)
        else:
            # Fetch using Version API from GitHub.
            version = self.version or "latest"
            try:
                self._fetch_version(version, destination)
            except Exception as err_from_version_approach:
                logger.warning(
                    f"No official release found for version '{version}'. "
                    "Use `ref:` instead of `version:` for release tags. "
                    "Checking for matching tags..."
                )

                # NOTE: When using ref-from-a-version, ensure
                #   it didn't create the destination along the way;
                #   else, the ref is cloned in the wrong spot.
                shutil.rmtree(destination, ignore_errors=True)
                try:
                    self._fetch_ref(version, destination)
                except Exception:
                    # NOTE: Ignore this error, it was merely a last attempt.
                    raise err_from_version_approach

    def _fetch_ref(self, ref: str, destination: Path):
        options = _version_to_options(ref)
        attempt = 0
        num_attempts = len(options)
        for ref in options:
            attempt += 1
            try:
                self._github_client.clone_repo(
                    self.org_name, self.repo_name, destination, branch=ref
                )
            except Exception:
                if attempt == num_attempts:
                    raise  # This error!

                # Try another option.
                continue

            else:
                # Was successful! Don't try anymore.
                break

    def _fetch_version(self, version: str, destination: Path):
        destination.mkdir(parents=True, exist_ok=True)
        options = _version_to_options(version)
        attempt = 0
        max_attempts = len(options)

        for vers in options:
            attempt += 1
            try:
                self._github_client.download_package(
                    self.org_name, self.repo_name, vers, destination
                )
            except Exception:
                if attempt == max_attempts:
                    raise  # This error!

                # Try another option.
                continue

            else:
                # Was successful! Don't try anymore.
                break


class NpmDependency(DependencyAPI):
    """
    A dependency from the Node Package Manager (NPM).

    Config example::

        dependencies:
          - name: safe-singleton-factory
            npm: "@gnosis.pm/safe-singleton-factory"
            version: 1.0.14
    """

    npm: Path
    """
    The NPM repo ID e.g. the organization name followed by the repo name,
    such as ``"@gnosis.pm/safe-singleton-factory"``.
    Note: Resolves to a 'path' after serialization.
    The package must already be installed!
    """

    version: Optional[str] = None
    """
    Specify the version, if not wanting to use discovered version
    from install.
    """

    @model_validator(mode="before")
    @classmethod
    def validate_local_npm(cls, model):
        # Resolves the relative path so if the dependency API
        # data moves, it will still work.
        npm = Path(model["npm"])
        if npm.is_absolute():
            return model

        elif "project" in model:
            # Just in case relative paths didn't get resolved.
            # Note: Generally, they should be resolved at model
            #  construction time, if parsing a config file normally.
            project = model.pop("project")
            if isinstance(project, str):
                project_path = Path(project)
            elif isinstance(project, Path):
                project_path = project
            else:
                project_path = project.path

            for base_path in (project_path, Path.home()):
                path = base_path / "node_modules" / npm
                if path.is_dir():
                    model["npm"] = npm = path
                    break

        return model

    @cached_property
    def version_id(self) -> str:
        if version := (
            self.version
            or self.version_from_installed_package_json
            or self.version_from_project_package_json
        ):
            return version

        raise ProjectError(
            f"Missing version for NPM dependency '{self.name}'. Have you run `npm install`?"
        )

    @property
    def package_id(self) -> str:
        return str(self.npm).split("node_modules")[-1].strip(os.path.sep)

    @cached_property
    def version_from_installed_package_json(self) -> Optional[str]:
        """
        The version from package.json in the installed package.
        Requires having run `npm install`.
        """
        return _get_version_from_package_json(self.npm)

    @cached_property
    def version_from_project_package_json(self) -> Optional[str]:
        """
        The version from your project's package.json, if exists.
        """
        return _get_version_from_package_json(
            self.local_project.path, dict_path=("dependencies", self.package_id)
        )

    @property
    def uri(self) -> str:
        return f"https://www.npmjs.com/package/{self.npm}/v/{self.version_id}"

    def fetch(self, destination: Path):
        if self.npm.is_dir():
            if destination.is_dir():
                destination = destination / self.name

            shutil.copytree(self.npm, destination)
        else:
            raise ProjectError(f"NPM package '{self.package_id}' not installed.")


def _get_version_from_package_json(
    base_path: Path, dict_path: Optional[Iterable[Union[str, Path]]] = None
) -> Optional[str]:
    package_json = base_path / "package.json"
    if not package_json.is_file():
        return None

    try:
        data = json.loads(package_json.read_text())
    except Exception as err:
        logger.warning(f"Failed to parse package.json: {err}")
        return None

    for key in dict_path or []:
        if key not in data:
            return None

        data = data[key]

    if isinstance(data, str):
        return data

    elif not isinstance(data, dict):
        return None

    return data.get("version")


# TODO: Rename to `PyPIDependency` in 0.9.
class PythonDependency(DependencyAPI):
    """
    A dependency installed from Python tooling, such as `pip`.
    """

    # TODO: Rename this `site_package_name` in 0.9.
    python: Optional[str] = None
    """
    The Python site-package name, such as ``"snekmate"``. Cannot use
    with ``pypi:``. Requires the dependency to have been installed
    either via ``pip`` or something alike.
    """

    pypi: Optional[str] = None
    """
    The ``pypi`` reference, such as ``"snekmate"``. Cannot use with
    ``python:``. When set, downloads the dependency from ``pypi``
    using HTTP directly (not ``pip``).
    """

    version: Optional[str] = None
    """
    Optionally specify the version expected to be installed.
    """

    @model_validator(mode="before")
    @classmethod
    def validate_model(cls, values):
        if "name" not in values:
            if name := values.get("python") or values.get("pypi"):
                values["name"] = name
            else:
                raise ValueError(
                    "Must set either 'pypi:' or 'python': when using Python dependencies"
                )

        return values

    @cached_property
    def path(self) -> Optional[Path]:
        if self.pypi:
            # Is pypi: specified; has no special path.
            return None

        elif python := self.python:
            try:
                return get_package_path(python)
            except ValueError as err:
                raise ProjectError(str(err)) from err

        return None

    @property
    def package_id(self) -> str:
        if pkg_id := (self.pypi or self.python):
            return pkg_id

        raise ProjectError("Must provide either 'pypi:' or 'python:' for python-base dependencies.")

    @property
    def version_id(self) -> str:
        if self.pypi:
            # Version available in package data.
            if not (vers := self.version_from_package_data or ""):
                # I doubt this is a possible condition, but just in case.
                raise ProjectError(f"Missing version from PyPI for package '{self.package_id}'.")

        elif self.python:
            try:
                vers = f"{metadata.version(self.package_id)}"
            except metadata.PackageNotFoundError as err:
                raise ProjectError(f"Dependency '{self.package_id}' not installed.") from err

            if spec_vers := self.version:
                if spec_vers != vers:
                    raise ProjectError(
                        "Dependency installed with mismatched version. "
                        f"Expecting '{self.version}' but has '{vers}'"
                    )

        else:
            raise ProjectError(
                "Must provide either 'pypi:' or 'python:' for python-base dependencies."
            )

        return vers

    @property
    def uri(self) -> str:
        if self.pypi:
            return self.download_archive_url

        elif self.python and (path := self.path):
            # Local site-package path.
            return path.as_uri()

        else:
            raise ProjectError(
                "Must provide either 'pypi:' or 'python:' for python-base dependencies."
            )

    @cached_property
    def package_data(self) -> dict:
        url = f"https://pypi.org/pypi/{self.package_id}/json"
        response = requests.get(url)

        try:
            response.raise_for_status()
        except requests.HTTPError as err:
            if err.response.status_code == 404:
                raise ProjectError(
                    f"Unknown dependency '{self.package_id}'. "
                    "Is it spelled correctly and available on PyPI? "
                    "For local Python packages, use the `python:` key."
                )
            else:
                raise ProjectError(
                    f"Problem downloading package data for '{self.package_id}': {err}"
                )

        return response.json()

    @cached_property
    def version_from_package_data(self) -> Optional[str]:
        return self.package_data.get("info", {}).get("version")

    @cached_property
    def download_archive_url(self) -> str:
        if not (version := self.version):
            if not (version := self.version_from_package_data):
                # Not sure this is possible, but just in case API data changes or something.
                raise ProjectError(f"Unable to find version for package '{self.package_id}'.")

        releases = self.package_data.get("releases", {})
        if version not in releases:
            raise ProjectError(f"Version '{version}' not found for package '{self.package_id}'.")

        # Find the first zip file in the specified release.
        for file_info in releases[version]:
            if file_info.get("packagetype") != "sdist":
                continue

            return file_info["url"]

        raise ProjectError(
            f"No zip file found for package '{self.package_id}' with version '{version}' on PyPI."
        )

    def fetch(self, destination: Path):
        if self.pypi:
            self._fetch_from_pypi(destination)
        elif path := self.path:
            # 'python:' key.
            _fetch_local(path, destination, config_override=self.config_override)

    def _fetch_from_pypi(self, destination: Path):
        archive_path = self._fetch_archive_file(destination)
        extract_archive(archive_path)
        archive_path.unlink(missing_ok=True)

    def _fetch_archive_file(self, destination) -> Path:
        logger.info(f"Fetching python dependency '{self.package_id}' from 'pypi.")
        download_url = self.download_archive_url
        filename = download_url.split("/")[-1]
        destination.mkdir(exist_ok=True, parents=True)
        archive_destination = destination / filename
        with requests.get(download_url, stream=True) as response:
            response.raise_for_status()
            with open(archive_destination, "wb") as file:
                for chunk in response.iter_content(chunk_size=8192):  # 8 KB
                    file.write(chunk)

        return archive_destination
