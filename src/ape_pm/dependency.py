import json
import os
import shutil
from collections.abc import Iterable
from functools import cached_property
from importlib import metadata
from pathlib import Path
from typing import Optional, Union

from pydantic import model_validator

from ape.api.projects import DependencyAPI
from ape.exceptions import ProjectError
from ape.logging import logger
from ape.managers.project import _version_to_options
from ape.utils import ManagerAccessMixin, clean_path, get_package_path, in_tempdir
from ape.utils._github import _GithubClient, github_client


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
    def branch_to_ref(cls, model):
        if "branch" in model and "ref" not in model:
            # Handle branch as an alias.
            model["ref"] = model.pop("branch")

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

    def __repr__(self):
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


class PythonDependency(DependencyAPI):
    """
    A dependency installed from Python, such as files published to PyPI.
    """

    python: str
    """
    The Python site-package name.
    """

    version: Optional[str] = None
    """
    Optionally specify the version expected to be installed.
    """

    @model_validator(mode="before")
    @classmethod
    def validate_model(cls, values):
        if "name" not in values and "python" in values:
            values["name"] = values["python"]

        return values

    @cached_property
    def path(self) -> Path:
        try:
            return get_package_path(self.python)
        except ValueError as err:
            raise ProjectError(str(err)) from err

    @property
    def package_id(self) -> str:
        return self.python

    @property
    def version_id(self) -> str:
        try:
            vers = f"{metadata.version(self.python)}"
        except metadata.PackageNotFoundError as err:
            raise ProjectError(f"Dependency '{self.python}' not installed.") from err

        if spec_vers := self.version:
            if spec_vers != vers:
                raise ProjectError(
                    "Dependency installed with mismatched version. "
                    f"Expecting '{self.version}' but has '{vers}'"
                )

        return vers

    @property
    def uri(self) -> str:
        return self.path.as_uri()

    def fetch(self, destination: Path):
        _fetch_local(self.path, destination, config_override=self.config_override)
