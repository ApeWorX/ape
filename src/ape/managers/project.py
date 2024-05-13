import json
import os
import random
import shutil
import tempfile
from collections.abc import Callable, Iterable, Iterator
from contextlib import contextmanager
from functools import cached_property, singledispatchmethod
from pathlib import Path
from typing import Any, Optional, Union, cast

from eth_typing import HexStr
from ethpm_types import ContractInstance as EthPMContractInstance
from ethpm_types import ContractType, PackageManifest, PackageMeta, Source
from ethpm_types.source import Compiler, ContractSource
from ethpm_types.utils import compute_checksum
from pydantic_core import Url

from ape.api.projects import ApeProject, DependencyAPI, ProjectAPI
from ape.contracts import ContractContainer, ContractInstance
from ape.exceptions import APINotImplementedError, ChainError, ProjectError
from ape.logging import logger
from ape.managers.base import BaseManager
from ape.managers.config import ApeConfig
from ape.utils.basemodel import (
    ExtraAttributesMixin,
    ExtraModelAttributes,
    ManagerAccessMixin,
    get_attribute_with_extras,
    only_raise_attribute_error,
)
from ape.utils.misc import SOURCE_EXCLUDE_PATTERNS, log_instead_of_fail
from ape.utils.os import (
    clean_path,
    create_tempdir,
    get_all_files_in_directory,
    get_full_extension,
    get_relative_path,
    path_match,
)


def path_to_source_id(path: Path, root_path: Path) -> str:
    return f"{get_relative_path(path.absolute(), root_path.absolute())}"


class SourceManager(BaseManager):
    def __init__(
        self,
        root_path: Path,
        get_contracts_path: Callable,
        exclude_globs: Optional[set[str]] = None,
    ):
        self.root_path = root_path
        self.get_contracts_path = get_contracts_path
        self.exclude_globs = exclude_globs or set()
        self._sources: dict[str, Source] = {}

    @log_instead_of_fail(default="<LocalSources>")
    def __repr__(self) -> str:
        path_str = f" {clean_path(self.get_contracts_path())}"
        return f"<LocalSources{path_str}>"

    def __len__(self) -> int:
        return len(list(self.paths))

    def __iter__(self) -> Iterator[str]:
        for path in self.paths:
            yield self._get_source_id(path)

    def __getitem__(self, source_id: str) -> Source:
        src = self.get(source_id)

        # NOTE: Can't use walrus operator here because empty Source objects
        #   are false-y.
        if src is None:
            raise IndexError(f"Source '{source_id}' not found.")

        return src

    def get(self, source_id: str) -> Optional[Source]:
        if source_id in self._sources:
            return self._sources[source_id]

        for path in self.paths:
            if self._get_source_id(path) == source_id:
                text: Union[str, dict]
                if path.is_file():
                    try:
                        text = path.read_text()
                    except Exception:
                        continue

                else:
                    text = {}

                src = Source.model_validate(text)
                self._sources[source_id] = src
                return src

        return None

    def items(self) -> Iterator[tuple[str, Source]]:
        for path in self.paths:
            source_id = self._get_source_id(path)
            yield source_id, self[source_id]

    def keys(self) -> Iterator[str]:
        for path in self.paths:
            yield self._get_source_id(path)

    def values(self) -> Iterator[Source]:
        for path in self.paths:
            source_id = self._get_source_id(path)
            yield self[source_id]

    @singledispatchmethod
    def __contains__(self, item) -> bool:
        raise APINotImplementedError(f"__contains__ not implemented for {type(item)}.")

    @__contains__.register
    def __contains_str(self, source_id: str) -> bool:
        for path in self.paths:
            if self._get_source_id(path) == source_id:
                return True

        return False

    @__contains__.register
    def __contains_path(self, source_path: Path) -> bool:
        for path in self.paths:
            if path == source_path:
                return True

        return False

    @property
    def paths(self) -> Iterator[Path]:
        """
        All contract sources paths.
        """
        contracts_folder = self.get_contracts_path()
        if not contracts_folder.is_dir():
            return

        all_files = get_all_files_in_directory(contracts_folder)
        for path in all_files:
            if self.is_excluded(path):
                continue

            yield path

    def is_excluded(self, path: Path) -> bool:
        for excl in self.exclude_globs:
            source_id = self._get_source_id(path)
            options = (str(path), path.name, source_id)
            for opt in options:
                if path_match(opt, excl):
                    return True

        registered = self.compiler_manager.registered_compilers
        is_file = path.is_file()
        suffix = get_full_extension(path)
        if is_file and suffix in registered:
            return False

        elif is_file and path.name.startswith("."):
            # Ignore random hidden files if they are known source types.
            return True

        # Likely from a source that doesn't have an installed compiler.
        return False

    def lookup(self, path_id: Union[str, Path]) -> Optional[Path]:
        """
        Look-up a path by given a sub-path or a source ID.

        Args:
            path_id (Union[str, Path]): Either part of a path
              or a source ID.

        Returns:
            Path: The full path to the source file.
        """
        input_path = Path(path_id)
        if input_path.is_file():
            # Already given an existing file.
            return input_path.absolute()

        input_stem = input_path.stem
        input_extension = get_full_extension(input_path) or None

        def find_in_dir(dir_path: Path, path: Path) -> Optional[Path]:
            # Try exact match with or without extension
            possible_matches = []
            contracts_folder = self.get_contracts_path()

            if path.is_absolute():
                full_path = path
            elif contracts_folder in (dir_path / path).parents:
                # Check if a file with an exact match exists.
                full_path = dir_path / path
            else:
                # User did not include contracts-prefix.
                full_path = contracts_folder / path

            if full_path.is_file():
                return full_path

            # Check for exact match with no given extension.
            if input_extension is None:
                if full_path.parent.is_dir():
                    for file in full_path.parent.iterdir():
                        if not file.is_file():
                            continue
                        elif not (file_ext := get_full_extension(file)):
                            continue

                        # Check exact match w/o extension.
                        prefix = file_ext.join(str(file).split(file_ext)[:-1])
                        if str(full_path) == prefix:
                            return file

                # Look for stem-only matches (last resort).
                for file_path in dir_path.rglob("*"):
                    if file_path.stem == input_stem:
                        possible_matches.append(file_path)

            # If we have possible matches, return the one with the closest relative path
            if possible_matches:
                # Prioritize the exact relative path or first match in the list
                possible_matches.sort(key=lambda p: len(str(p.relative_to(dir_path))))
                return possible_matches[0]

            return None

        # Derive the relative path from the given key_contract_path.
        relative_path = input_path.relative_to(input_path.anchor)
        return find_in_dir(self.root_path, relative_path)

    def _get_source_id(self, path: Path) -> str:
        return path_to_source_id(path, self.root_path)

    def _get_path(self, source_id: str) -> Path:
        return self.root_path / source_id


class ContractManager(BaseManager):
    """
    Local contract-type loader.
    """

    def __init__(self, project: "LocalProject", sources: SourceManager):
        self.project = project
        self.sources = sources

    @log_instead_of_fail(default="<ContractManager>")
    def __repr__(self) -> str:
        folder = self.project.contracts_folder
        folder_str = f" {clean_path(folder)}" if folder else ""
        return f"<Contracts{folder_str}>"

    def __contains__(self, contract_name: str) -> bool:
        return self.get(contract_name) is not None

    def __getitem__(self, contract_name: str) -> ContractContainer:
        if contract := self.get(contract_name):
            return contract

        raise IndexError(f"Contract '{contract_name}' not found.")

    def __iter__(self) -> Iterator[str]:
        self._compile_missing_contracts(self.sources.paths)
        if contract_types := self.project.manifest.contract_types:
            for ct in contract_types.values():
                if ct.name:
                    yield ct.name

    def get(self, name: str, compile_missing: bool = True) -> Optional[ContractContainer]:
        existing_types = self.project.manifest.contract_types or {}
        if contract_type := existing_types.get(name):
            source_id = contract_type.source_id or ""
            if source_id in self.sources and self.detect_change(source_id):
                # Previous cache is outdated.
                compiled = {
                    ct.name: ct
                    for ct in self.compiler_manager.compile(source_id, project=self.project)
                    if ct.name
                }
                if compiled:
                    self.project._update_contract_types(compiled)
                    if name in compiled:
                        return ContractContainer(compiled[name])

            elif source_id in self.sources:
                # Cached and already compiled.
                return ContractContainer(contract_type)

        if compile_missing:
            # Try again after compiling all missing.
            self._compile_missing_contracts(self.sources.paths)
            return self.get(name, compile_missing=False)

        return None

    def keys(self) -> Iterator[str]:
        # dict-like behavior.
        yield from self

    def values(self) -> Iterator[ContractContainer]:
        # dict-like behavior.
        for name in self:
            yield self[name]

    def _compile_missing_contracts(self, paths: Iterable[Union[Path, str]]):
        non_compiled_sources = self._get_needs_compile(paths)
        self._compile_contracts(non_compiled_sources)

    def _get_needs_compile(self, paths: Iterable[Union[Path, str]]) -> Iterable[Path]:
        for path in paths:
            if self.detect_change(path):
                if isinstance(path, str):
                    yield self.sources._get_path(path)
                else:
                    yield path

    def _compile_contracts(self, paths: Iterable[Union[Path, str]]):
        if not (
            new_types := {
                ct.name: ct
                for ct in self.compiler_manager.compile(paths, project=self.project)
                if ct.name
            }
        ):
            return

        existing_types = self.project.manifest.contract_types or {}
        contract_types = {**existing_types, **new_types}
        self.project._update_contract_types(contract_types)

    def load_contracts(self, use_cache: bool = True) -> dict[str, ContractContainer]:
        return {
            c.contract_type.name: c
            for c in self.compile_all(use_cache=use_cache)
            if c.contract_type.name
        }

    def compile_all(self, use_cache: bool = True) -> Iterator[ContractContainer]:
        if sources := self.sources:
            yield from self.compile(sources.paths, use_cache=use_cache)

    def compile(
        self, paths: Union[Path, str, Iterable[Union[Path, str]]], use_cache: bool = True
    ) -> Iterator[ContractContainer]:
        path_ls = list([paths] if isinstance(paths, (Path, str)) else paths)
        if not path_ls:
            return

        # Compile necessary contracts.
        needs_compile = list(self._get_needs_compile(path_ls) if use_cache else path_ls)
        if needs_compile:
            self._compile_contracts(needs_compile)

        src_ids = [f"{get_relative_path(Path(p).absolute(), self.project.path)}" for p in path_ls]
        for contract_type in (self.project.manifest.contract_types or {}).values():
            if contract_type.source_id and contract_type.source_id in src_ids:
                yield ContractContainer(contract_type)

    def detect_change(self, path: Union[Path, str]) -> bool:
        if not (existing_types := (self.project.manifest.contract_types or {}).values()):
            return True  # Nothing compiled yet.

        source_id: str
        if isinstance(path, Path):
            path = path
            source_id = self.sources._get_source_id(path)
        else:
            source_id = str(path)  # str wrap for mypy
            path = self.sources._get_path(path)

        if source_id not in (self.project.manifest.sources or {}) or source_id not in (
            x.source_id for x in existing_types if x.source_id
        ):
            return True  # New file.

        # ethpm_types strips trailing white space and ensures
        # a newline at the end so content so `splitlines()` works.
        # We need to do the same here for to prevent the endless recompiling bug.
        text = path.read_text("utf8").rstrip()
        content = f"{text}\n" if text else ""

        cached_source = (self.project.manifest.sources or {}).get(source_id)
        assert cached_source is not None
        missing_source_text = cached_source.content in (None, "")

        # NOTE: Have to handle this case separately because otherwise
        #   ethpm_types attempts to fetch content.
        if missing_source_text and content == "":
            return False  # Emptiness
        elif missing_source_text:
            return True  # New source text when was previously empty.

        cached_checksum = cached_source.calculate_checksum()
        checksum = compute_checksum(content.encode("utf8"), algorithm=cached_checksum.algorithm)

        # The file has not changed if the hashes equal (and thus 'is_compiled')
        return checksum != cached_checksum.hash


class Dependency(BaseManager, ExtraAttributesMixin):
    """
    A wrapper around a dependency.
    Users will not create this class directly but access
    them from ``project.dependencies``.
    """

    def __init__(self, api: DependencyAPI, project: Optional["ProjectManager"] = None):
        self.api = api
        # This is the base project using this dependency.
        self.base_project = project or self.project_manager
        # When installed (and set, lazily), this is the dependency project.
        self._installation: Optional["ProjectManager"] = None

    @log_instead_of_fail(default="<Dependency>")
    def __repr__(self) -> str:
        return f"<{self.api.package_id}@{self.api.version_id}>"

    @only_raise_attribute_error
    def __getattr__(self, name: str) -> Any:
        return get_attribute_with_extras(self, name)

    def __ape_extra_attributes__(self) -> Iterator[ExtraModelAttributes]:
        yield ExtraModelAttributes(name="project", attributes=lambda: self.project)

    @property
    def name(self) -> str:
        return self.api.name

    @property
    def package_id(self) -> str:
        return self.api.package_id

    @property
    def version(self) -> str:
        return self.api.version_id

    @property
    def project(self) -> "ProjectManager":
        return self.install()

    @property
    def _cache(self) -> "PackagesCache":
        return self.base_project.dependencies.packages_cache

    @property
    def project_path(self) -> Path:
        return self._cache.get_project_path(self.package_id, self.version)

    @property
    def manifest_path(self) -> Path:
        return self._cache.get_manifest_path(self.package_id, self.version)

    @property
    def uri(self) -> str:
        return self.api.uri

    def install(
        self, use_cache: bool = True, config_override: Optional[dict] = None
    ) -> "ProjectManager":
        config_override = {**(self.api.config_override or {}), **(config_override or {})}
        project = None

        if self._installation is not None and use_cache:
            if config_override:
                self._installation.reconfigure(**config_override)

            return self._installation

        elif (not self.project_path.is_dir() and not self.manifest_path.is_file()) or not use_cache:
            # Fetch the project if needed.
            shutil.rmtree(self.project_path, ignore_errors=True)
            self.project_path.parent.mkdir(parents=True, exist_ok=True)
            self.api.fetch(self.project_path)

        # Set name / version for the project, if it needs.
        if "name" not in config_override:
            config_override["name"] = self.api.name
        if "version" not in config_override:
            config_override["version"] = self.api.version_id

        if self.project_path.is_dir():
            # Handle if given a manifest only.
            paths = [x for x in self.project_path.iterdir()]
            if len(paths) > 0:
                suffix = get_full_extension(paths[0])
                if len(paths) == 1 and suffix == ".json":
                    path = paths[0]
                    try:
                        manifest = PackageManifest.model_validate_json(path.read_text())
                    except Exception:
                        # False alarm.
                        pass
                    else:
                        # Using a manifest project, unless this is just emptiness.
                        if (
                            manifest.sources
                            or manifest.contract_types
                            or manifest.name
                            or manifest.version
                        ):
                            project = Project.from_manifest(
                                manifest, config_override=config_override
                            )

            if project is None:
                # Using an unpacked local-project.
                project = LocalProject(
                    self.project_path,
                    manifest_path=self.manifest_path,
                    config_override=config_override,
                )

        elif self.manifest_path.is_file():
            # Manifest-only project with manifest populated and not project-dir.
            project = Project.from_manifest(self.manifest_path, config_override=config_override)

        else:
            # Project dir is missing, but we know the manifest path at least exists by this point.
            raise ProjectError("Project install failed.")

        # Cache for next time.
        self._installation = project

        # Also, install dependencies of dependencies.
        for dependency in project.dependencies.specified:
            dependency.install(use_cache=use_cache, config_override=config_override)

        return project

    def uninstall(self):
        self._cache.remove(self.package_id, self.version)
        self._installation = None

    def compile(self, use_cache: bool = True) -> dict[str, ContractContainer]:
        if self.api.config_override:
            # Ensure is using most up-to-date config override.
            self.project.reconfigure(**self.api.config_override)

        return self.project.load_contracts(use_cache=use_cache)

    def unpack(self, path: Path):
        """
        Move dependencies into a .cache folder.
        Ideal for tmp-projects.
        """
        self._unpack(path, set())

    def _unpack(self, path: Path, tracked: set[str]):
        key = self.project_id
        if key in tracked:
            return

        tracked.add(key)
        folder = path / self.name / self.version

        if folder.is_dir():
            # This dependency (and its dependencies) were already handled!
            return

        if sources := self.project.sources:
            for source_id, src in sources.items():
                src_path = folder / source_id
                src_path.parent.mkdir(parents=True, exist_ok=True)
                if src_path.is_file():
                    continue

                src_path.write_text(str(src.content))

        # Unpack dependencies of dependencies (if they aren't already).
        for dependency in self.project.dependencies.specified:
            dependency._unpack(path, tracked=tracked)


class PackagesCache(ManagerAccessMixin):
    def __init__(self):
        self._api_cache: dict[str, DependencyAPI] = {}
        self._project_cache: dict[str, "ProjectManager"] = {}

    def __contains__(self, package: str) -> bool:
        return package in self.installed_package_names

    @property
    def root(self) -> Path:
        return self.config_manager.DATA_FOLDER / "packages"

    @property
    def projects_folder(self) -> Path:
        return self.root / "projects"

    @property
    def api_folder(self) -> Path:
        return self.root / "api"

    @property
    def manifests_folder(self) -> Path:
        return self.root / "manifests"

    @property
    def installed_package_names(self) -> set[str]:
        return {x.name for x in self.projects_folder.iterdir()}

    def get_project_path(self, package_id: str, version: str) -> Path:
        """
        Path to the dir of the cached project.
        """
        package_id_name = package_id.replace("/", "_")
        version_name = version.replace(".", "_")
        return self.projects_folder / package_id_name / version_name

    def get_manifest_path(self, package_id: str, version: str) -> Path:
        """
        Path to the manifest filepath the dependency project uses
        as a base.
        """
        package_id_name = package_id.replace("/", "_")
        version_name = f"{version.replace('.', '_')}.json"
        return self.manifests_folder / package_id_name / version_name

    def cache_api(self, api: DependencyAPI):
        """
        Cache a dependency JSON for usage outside of the project.
        """
        package_id_name = api.package_id.replace("/", "_")
        version_name = api.version_id.replace(".", "_").replace("/", "_")
        api_file = self.api_folder / package_id_name / f"{version_name}.json"
        api_file.parent.mkdir(parents=True, exist_ok=True)
        api_file.unlink(missing_ok=True)
        json_text = api.model_dump_json(by_alias=True, mode="json")
        api_file.write_text(json_text)

    def remove(self, package_id: str, version: str):
        project_path = self.get_project_path(package_id, version)
        if project_path.is_dir():
            # Delete version directory (containing the project files)
            shutil.rmtree(project_path)
        if (
            project_path.parent.is_dir()
            and len([x for x in project_path.parent.iterdir() if x.is_dir()]) == 0
        ):
            # Delete empty dependency root folder.
            shutil.rmtree(project_path.parent)

        package_id_name = package_id.replace("/", "_")
        version_name = f"{version.replace('.', '_')}.json"
        api_file = self.api_folder / package_id_name / version_name
        api_file.unlink(missing_ok=True)
        manifest_file = self.manifests_folder / package_id_name / version_name
        manifest_file.unlink(missing_ok=True)


class DependencyManager(BaseManager):
    """
    Manage dependencies for an Ape project.
    Note: Every project gets its own dependency-set (DependencyManager).
    """

    def __init__(self, project: Optional["ProjectManager"] = None):
        self.project = project or self.project_manager

    @log_instead_of_fail(default="<DependencyManager>")
    def __repr__(self) -> str:
        return f"<DependencyManager project={clean_path(self.project.path)}>"

    def __iter__(self) -> Iterator[Dependency]:
        yield from self.specified

    def __len__(self) -> int:
        # NOTE: Using the config value keeps use lazy and fast.
        path = self.packages_cache.api_folder
        if not path.is_dir():
            return 0

        count = 0
        for dep in self.packages_cache.api_folder.iterdir():
            if not dep.is_dir():
                continue

            count += sum(f.is_file() and f.suffix == ".json" for f in dep.iterdir())

        return count

    def __getitem__(self, name: str) -> dict[str, "ProjectManager"]:
        result: dict[str, "ProjectManager"] = {}
        for dependency in self.installed:
            if dependency.name != name:
                continue

            result[dependency.version] = dependency.project

        if result:
            return result

        # Try installing specified.
        if versions := {d.version: d.project for d in self.specified if d.name == name}:
            return versions

        return {}

    def __contains__(self, name: str) -> bool:
        for dependency in self.installed:
            if name == dependency.name:
                return True

        return False

    def keys(self) -> Iterator[str]:
        _ = [x for x in self.specified]  # Install specified if needed.
        for dependency in self.installed:
            yield dependency.name

    def items(self) -> Iterator[tuple[str, dict[str, "ProjectManager"]]]:
        _ = [x for x in self.specified]  # Install specified if needed.
        for dependency in self.installed:
            yield dependency.name, {dependency.version: dependency.project}

    def values(self) -> Iterator[dict[str, "ProjectManager"]]:
        _ = [x for x in self.specified]  # Install specified if needed.
        for dependency in self.installed:
            yield {dependency.version: dependency.project}

    @property
    def config(self) -> ApeConfig:
        return self.project.config

    @cached_property
    def packages_cache(self) -> PackagesCache:
        """
        Where all dependency files go.
        """
        return PackagesCache()

    @cached_property
    def types(self) -> dict[str, type[DependencyAPI]]:
        dependency_classes: dict[str, type[DependencyAPI]] = {}

        for _, (config_key, dependency_class) in self.plugin_manager.dependencies:
            assert issubclass(dependency_class, DependencyAPI)  # For mypy
            dependency_classes[config_key] = dependency_class

        return dependency_classes

    @property
    def specified(self) -> Iterator[Dependency]:
        """
        All dependencies specified in the config.
        """
        for data in self.config.dependencies:
            api = self.decode_dependency(data)
            self._install(api)
            yield self.get_dependency(api.name, api.version_id)

    @property
    def installed(self) -> Iterator[Dependency]:
        """
        All installed dependencies, regardless of their project
        affiliation.
        """
        if not self.packages_cache.api_folder.is_dir():
            return

        for package_versions in self.packages_cache.api_folder.iterdir():
            if not package_versions.is_dir():
                continue

            for api_file in package_versions.iterdir():
                if not api_file.is_file():
                    continue

                data = json.loads(api_file.read_text())
                api = self.decode_dependency(data)
                if api.name == self.project.name:
                    # Don't include self as a dependency
                    # (happens when compiling a dependency)
                    continue

                yield Dependency(api, project=self.project)

    @property
    def uri_map(self) -> dict[str, Url]:
        """
        A map of URIs for filling out the dependencies
        field in a package manifest.
        NOTE: Only uses specified dependencies! Make sure
        you are specifying all the needed dependencies in your
        config file instead of only relying on globally-installed
        packages.
        """
        return {dep.name: Url(dep.api.uri) for dep in self.specified}

    def get(
        self, name: str, version: str, allow_install: bool = True
    ) -> Optional["ProjectManager"]:
        if dependency := self._get(name, version, allow_install=allow_install, checked=set()):
            return dependency.project

        return None

    def _get(
        self, name: str, version: str, allow_install: bool = True, checked: Optional[set] = None
    ) -> Optional[Dependency]:
        checked = checked or set()

        # Check already-installed first to prevent having to install anything.
        name_matches = []
        for dependency in self.installed:
            if dependency.package_id == name and dependency.version == version:
                # If matching package-id, use that no matter what.
                return dependency

            elif dependency.name == name and dependency.version == version:
                name_matches.append(dependency)

        if name_matches:
            if len(name_matches) == 1:
                # Return match-by-name after full loop in case was checking by
                # package ID, which is more precise.
                return name_matches[0]

        # Check if not installed.
        name_matches = []
        if allow_install:
            # NOTE: If any specified dependencies are not installed,
            #  they will be now.
            for dependency in self.specified:
                if dependency.package_id == name and dependency.version == version:
                    return dependency

                elif dependency.name == name and dependency.version == version:
                    name_matches.append(dependency)

        if name_matches:
            return name_matches[0]

        # Was not found in this project's dependencies.
        checked.add(self.project.project_id)

        # Still not found - check dependencies of dependencies.
        # NOTE: Purposely checking all specified first.
        for dependency in [*self.specified, *self.installed]:
            sub_project = dependency.project
            key = sub_project.project_id
            if key in checked:
                continue

            checked.add(key)
            sub_dependency = sub_project.dependencies._get(name, version, checked=checked)
            return sub_dependency

        return None

    def get_versions(self, name: str) -> Iterator[Dependency]:
        """
        Get all installed versions of a dependency.

        Args:
            name (str): The name of the dependency.

        Returns:
            Iterator[:class:`~ape.managers.project.Dependency`]
        """
        # First, check specified. Note: installs if needed.
        versions_yielded = set()
        for dependency in self.specified:
            if dependency.name == name:
                if dependency.version in versions_yielded:
                    continue

                yield dependency
                versions_yielded.add(dependency.version)

        # Yield any remaining installed.
        for dependency in self.installed:
            if dependency.name == name:
                if dependency.version in versions_yielded:
                    continue

                yield dependency
                versions_yielded.add(dependency.version)

    def get_dependency(self, name: str, version: str) -> Dependency:
        version_options = [version]
        if version.startswith("v"):
            version_options.append(version[1:])
        else:
            version_options.append(f"v{version}")

        def try_get():
            for opt in version_options:
                if dependency := self._get(name, opt):
                    return dependency

        if res := try_get():
            return res

        # Try installing first.
        self.install()

        if res := try_get():
            return res

        raise ProjectError(f"Dependency '{name}' with version '{version}' not found.")

    def decode_dependency(self, item: dict) -> DependencyAPI:
        for key, cls in self.types.items():
            if key in item:
                return cls.model_validate(item)

        name = item.get("name") or json.dumps(item)  # NOTE: Using 'or' for short-circuit eval
        raise ProjectError(
            f"No installed dependency API that supports '{name}'. "
            f"Keys={', '.join([x for x in item.keys()])}"
        )

    def add(self, dependency: Union[dict, DependencyAPI]) -> Dependency:
        api = self.decode_dependency(dependency) if isinstance(dependency, dict) else dependency
        self.packages_cache.cache_api(api)
        return self.get_dependency(api.name, api.version_id)

    def install(self, *dependencies: Union[dict, DependencyAPI], use_cache: bool = True):
        """
        Install dependencies.
        """
        if dependencies:
            for item in dependencies:
                self._install(item, use_cache=use_cache)

        else:
            # Install all project's.
            _ = [x for x in self.specified]

    def _install(self, item: Union[dict, DependencyAPI], use_cache: bool = True):
        dependency = self.add(item)
        dependency.install(use_cache=use_cache)

    def unpack(self, path: Path):
        """
        Move dependencies into a .cache folder.
        Ideal for isolated, temporary projects.
        """
        cache_folder = path / ".cache"
        for dependency in self.specified:
            dependency.unpack(cache_folder)


def load_manifest(path: Union[Path, str]) -> PackageManifest:
    path = Path(path)
    return (
        PackageManifest.model_validate_json(path.read_text())
        if path.is_file()
        else PackageManifest()
    )


class ProjectManager(ExtraAttributesMixin, BaseManager):
    """
    The root project manager in Ape that can also create other projects.
    """

    def __new__(cls, *args, **kwargs):
        if cls is ProjectManager:
            # Using `ape.Project(path)`.
            return super(cls, LocalProject).__new__(LocalProject)

        elif len(args) >= 1 and isinstance(args[0], PackageManifest):
            # Using `ape.Project.from_manifest()`.
            return super(ProjectManager, Project).__new__(Project)

        else:
            # Using LocalProject.__init__ (internal).
            return super(ProjectManager, LocalProject).__new__(LocalProject)

    @log_instead_of_fail(default="<ProjectManager>")
    def __repr__(self) -> str:
        return repr(self._project)

    @only_raise_attribute_error
    def __getattr__(self, name: str) -> Any:
        return get_attribute_with_extras(self, name)

    def __ape_extra_attributes__(self) -> Iterator[ExtraModelAttributes]:
        # NOTE: This causes attributes to use the singleton local project.
        #   However, you can still create additional projects via the
        #   factory mixin methods.
        yield ExtraModelAttributes(name="contracts", attributes=lambda: self._project)

    @cached_property
    def _project(self) -> "LocalProject":
        return LocalProject(self.path)

    @classmethod
    def from_manifest(
        cls, manifest: Union[PackageManifest, Path, str], config_override: Optional[dict] = None
    ) -> "Project":
        """
        Create an Ape project using only a manifest.

        Args:
            manifest (Union[PackageManifest, Path, str]): Either a manifest or a
              path to a manifest file.
            config_override (Optional[Dict]): Optionally provide a config override.

        Returns:
            :class:`~ape.managers.project.ProjectManifest`
        """
        return Project.from_manifest(manifest, config_override=config_override)

    @classmethod
    @contextmanager
    def create_temporary_project(
        cls, config_override: Optional[dict] = None
    ) -> Iterator["LocalProject"]:
        with create_tempdir() as path:
            yield LocalProject(path, config_override=config_override)


class Project(ProjectManager):
    """
    Base class for projects. Projects can come from either
    manifests or local source-paths.
    """

    def __init__(self, manifest: PackageManifest, config_override: Optional[dict] = None):
        self._manifest = manifest
        self._config_override = config_override or {}

    @log_instead_of_fail(default="<ProjectManager>")
    def __repr__(self) -> str:
        name = f" {self.project_id}"
        # NOTE: 'Project' is meta for 'ProjectManager' (mixin magic).
        return f"<ProjectManager{name}>"

    @only_raise_attribute_error
    def __getattr__(self, item: str) -> Any:
        try:
            return get_attribute_with_extras(self, item)
        except AttributeError as err:
            message = getattr(err, "message", str(err))
            did_append = False

            for src_id in self.sources or {}:
                path = Path(src_id)
                # Possibly, the user was trying to use a file name instead.
                if path.stem != item:
                    continue

                message = (
                    f"{message} However, there is a source file named '{path.name}', "
                    "did you mean to reference a contract name from this source file?"
                )
                did_append = True
                break

            # Possibly, the user does not have compiler plugins installed or working.

            if isinstance(self, LocalProject):
                missing_exts = set()
                for src_id in self.sources:
                    if ext := src_id.split(".")[-1]:
                        if f".{ext}" not in self.compiler_manager.registered_compilers:
                            missing_exts.add(f".{ext}")

                if missing_exts:
                    start = "Else, could" if did_append else "Could"
                    message = (
                        f"{message} {start} it be from one of the "
                        "missing compilers for extensions: " + f'{", ".join(sorted(missing_exts))}?'
                    )

            err.args = (message,)
            raise  # The same exception (keep the stack the same height).

    def __contains__(self, item):
        return item in self.contracts

    @property
    def name(self) -> str:
        if name := self.config.get("name"):
            return name
        elif name := self.manifest.name:
            return name

        return f"unknown-project-{random.randint(100_000, 999_999)}"

    @property
    def version(self) -> str:
        if version := self._config_override.get("version"):
            return version

        elif version := self.manifest.version:
            return version

        else:
            return "0.1.0"

    @property
    def project_id(self) -> str:
        return f"{self.name}_{self.version}"

    @property
    def is_compiled(self) -> bool:
        """
        True if the project is compiled at all. Does not
        ensure the compilation is up-to-date.
        """
        return (self._manifest.contract_types or None) is not None

    @classmethod
    def from_manifest(
        cls, manifest: Union[PackageManifest, Path, str], config_override: Optional[dict] = None
    ) -> "Project":
        config_override = config_override or {}
        manifest = load_manifest(manifest) if isinstance(manifest, (Path, str)) else manifest
        return Project(manifest, config_override=config_override)

    def __ape_extra_attributes__(self) -> Iterator[ExtraModelAttributes]:
        yield ExtraModelAttributes(
            name="contracts",
            attributes=lambda: self.contracts,
            include_getitem=True,
        )
        yield ExtraModelAttributes(
            name="manifest",
            attributes=lambda: self.manifest,
            include_getitem=True,
        )

    @property
    def manifest(self) -> PackageManifest:
        return self._manifest

    @cached_property
    def dependencies(self) -> DependencyManager:
        """
        Project dependencies.
        """
        return DependencyManager(project=self)

    @cached_property
    def config(self) -> ApeConfig:
        return ApeConfig.from_manifest(self.manifest, **self._config_override)

    @contextmanager
    def isolate_in_tempdir(self, **config_override) -> Iterator["LocalProject"]:
        """
        Clone this project to a temporary directory and return
        its project.
        """
        config_override = config_override or {}
        name = config_override.get("name", self.name)
        with create_tempdir(name=name) as path:
            yield self.unpack(path, config_override=config_override)

    @contextmanager
    def temp_config(self, **config):
        existing_overrides = self._config_override or {}
        self.reconfigure(**config)
        yield
        self.reconfigure(**existing_overrides)

    def get(self, name: str) -> Optional[ContractContainer]:
        return self.contracts.get(name)

    def unpack(self, destination: Path, config_override: Optional[dict] = None) -> "LocalProject":
        """
        Unpack the project to a location using the information
        from the manifest. Converts a manifest-based project
        to a local one.
        """

        config_override = {**self._config_override, **(config_override or {})}
        sources = self.sources or {}

        # Unpack contracts.
        for source_id, src in sources.items():
            path = destination / source_id
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(str(src.content))

        # Unpack config file.
        self.config.write_to_disk(destination / "ape-config.yaml")

        return LocalProject(destination, config_override=config_override)

    def update_manifest(self, **kwargs):
        """
        Change manifest values. Overwrites.

        **kwargs: Top-level manifest attributes.
        """
        for k, v in kwargs.items():
            setattr(self._manifest, k, v)

    def add_compiler_data(self, compiler_data: Iterable[Compiler]) -> list[Compiler]:
        """
        Add compiler data to the existing cached manifest.

        Args:
            compiler_data (Iterable[``ethpm_types.Compiler``]): Compilers to add.

        Returns:
            List[``ethpm_types.source.Compiler``]: The full list of compilers.
        """
        # Validate given data.
        given_compilers = set(compiler_data)
        num_compilers = len([x for x in compiler_data])
        if len(given_compilers) != num_compilers:
            raise ProjectError(
                f"`{self.add_compiler_data.__name__}()` was given multiple of the same compiler. "
                "Please filter inputs."
            )

        # Filter out given compilers without contract types.
        given_compilers = {c for c in given_compilers if c.contractTypes}
        if len(given_compilers) != num_compilers:
            logger.warning(
                f"`{self.add_compiler_data.__name__}()` given compilers without contract types. "
                "Ignoring these inputs."
            )

        for given_compiler in given_compilers:
            other_given_compilers = [c for c in given_compilers if c != given_compiler]
            contract_types_from_others = [
                n for c in other_given_compilers for n in (c.contractTypes or [])
            ]

            collisions = {
                n for n in (given_compiler.contractTypes or []) if n in contract_types_from_others
            }
            if collisions:
                collide_str = ", ".join(collisions)
                raise ProjectError(f"Contract type(s) '{collide_str}' collision across compilers.")

        new_types = [n for c in given_compilers for n in (c.contractTypes or [])]

        # Merge given compilers with existing compilers.
        existing_compilers = self.manifest.compilers or []

        # Existing compilers remaining after processing new compilers.
        remaining_existing_compilers: list[Compiler] = []

        for existing_compiler in existing_compilers:
            find_iter = iter(x for x in compiler_data if x == existing_compiler)

            if matching_given_compiler := next(find_iter, None):
                # Compiler already exists in the system, possibly with different contract types.
                # Merge contract types.
                matching_given_compiler.contractTypes = list(
                    {
                        *(existing_compiler.contractTypes or []),
                        *(matching_given_compiler.contractTypes or []),
                    }
                )
                # NOTE: Purposely we don't add the exising compiler back,
                #   as it is the same as the given compiler, (meaning same
                #   name, version, and settings), and we have
                #   merged their contract types.

                continue

            else:
                # Filter out contract types added now under a different compiler.
                existing_compiler.contractTypes = [
                    c for c in (existing_compiler.contractTypes or []) if c not in new_types
                ]

                # Clear output selection for new types, since they are present in the new compiler.
                if existing_compiler.settings and "outputSelection" in existing_compiler.settings:
                    new_src_ids = {
                        (self.manifest.contract_types or {})[x].source_id
                        for x in new_types
                        if x in (self.manifest.contract_types or {})
                        and (self.manifest.contract_types or {})[x].source_id is not None
                    }
                    existing_compiler.settings["outputSelection"] = {
                        k: v
                        for k, v in existing_compiler.settings["outputSelection"].items()
                        if k not in new_src_ids
                    }

                # Remove compilers without contract types.
                if existing_compiler.contractTypes:
                    remaining_existing_compilers.append(existing_compiler)

        # Use Compiler.__hash__ to remove duplicated.
        # Also, sort for consistency.
        compilers = sorted(
            list({*remaining_existing_compilers, *compiler_data}),
            key=lambda x: f"{x.name}@{x.version}",
        )
        self.update_manifest(compilers=compilers)
        return self._manifest.compilers or compilers  # for mypy.

    @property
    def contracts(self) -> dict[str, ContractContainer]:
        return self.load_contracts()

    def load_contracts(
        self, *source_ids: Union[str], use_cache: bool = True
    ) -> dict[str, ContractContainer]:
        result = {
            ct.name: ct
            for ct in ((self.manifest.contract_types or {}) if use_cache else {}).values()
            if ct.name
        }
        compiled_source_ids = {ct.source_id for ct in result.values() if ct.source_id}
        source_iter: Iterable = source_ids or list(self.manifest.sources or {})
        source_iter = [x if isinstance(x, str) else f"{x}" for x in source_iter]
        missing_sources = set()
        for src_id in source_iter:
            if src_id not in compiled_source_ids:
                missing_sources.add(src_id)

        missing_sources_can_compile = {
            s
            for s in missing_sources
            if get_full_extension(Path(s)) in self.compiler_manager.registered_compilers
        }
        if missing_sources_can_compile:
            # Attempt to compile to get missing sources.
            with self.isolate_in_tempdir() as temp_project:
                new_contracts = {
                    n: c.contract_type
                    for n, c in temp_project.load_contracts(*missing_sources_can_compile).items()
                }

            if new_contracts:
                self._update_contract_types(new_contracts)
                result = {**result, **new_contracts}

        return {n: ContractContainer(ct) for n, ct in result.items()}

    def _update_contract_types(self, contract_types: dict[str, ContractType]):
        self._manifest.contract_types = {**(self._manifest.contract_types or {}), **contract_types}
        self.update_manifest(
            contract_types=self._manifest.contract_types, sources=dict(self.sources)
        )

    def reconfigure(self, **overrides):
        """
        Change a project's config.

        Args:
            **overrides: Config key-value pairs. Completely overridesfe
              existing.
        """

        if "config" in self.__dict__:
            # Delete cached property.
            del self.__dict__["config"]

        self._config_override = overrides
        _ = self.config

    def extract_manifest(self) -> PackageManifest:
        return self.manifest


class DeploymentManager(ManagerAccessMixin):
    def __init__(self, project: "LocalProject"):
        self.project = project

    @property
    def cache_folder(self) -> Path:
        return self.config_manager.DATA_FOLDER / "deployments"

    @property
    def instance_map(self) -> dict[str, dict[str, EthPMContractInstance]]:
        """
        The mapping needed for deployments publishing in an ethpm manifest.
        """
        result: dict[str, dict[str, EthPMContractInstance]] = {}
        if not self.cache_folder.is_dir():
            return result

        for ecosystem_path in self.cache_folder.iterdir():
            if not ecosystem_path.is_dir():
                continue

            chain = ecosystem_path.name
            for deployment in ecosystem_path.iterdir():
                if not self._is_deployment(deployment):
                    continue

                instance = EthPMContractInstance.model_validate_json(deployment.read_text())
                if not instance.block:
                    continue

                bip122_uri = f"blockchain://{chain}/block/{instance.block.replace('0x', '')}"
                if bip122_uri in result:
                    result[bip122_uri][deployment.name] = instance
                else:
                    result[bip122_uri] = {deployment.name: instance}

        return result

    def track(self, contract: ContractInstance):
        """
        Indicate that a contract deployment should be included in the package manifest
        upon publication.

        **NOTE**: Deployments are automatically tracked for contracts. However, only
        deployments passed to this method are included in the final, publishable manifest.

        Args:
            contract (:class:`~ape.contracts.base.ContractInstance`): The contract
              to track as a deployment of the project.
        """

        if self.provider.network.is_dev:
            raise ProjectError("Can only publish deployments on a live network.")

        elif not (contract_name := contract.contract_type.name):
            raise ProjectError("Contract name required when publishing.")

        receipt = None
        err_msg = f"Contract '{contract_name}' transaction receipt is unknown."
        try:
            if creation := contract.creation_metadata:
                receipt = creation.receipt

        except ChainError as err:
            raise ProjectError(err_msg) from err

        if not receipt:
            raise ProjectError(err_msg)

        block_number = receipt.block_number
        block_hash_bytes = self.provider.get_block(block_number).hash
        if not block_hash_bytes:
            # Mostly for mypy, not sure this can ever happen.
            raise ProjectError(
                f"Block hash containing transaction for '{contract_name}' "
                f"at block_number={block_number} is unknown."
            )

        block_hash = block_hash_bytes.hex()
        contract_type_str = (
            f"{contract.contract_type.source_id}:{contract_name}"
            if contract.contract_type.source_id
            else contract_name
        )
        artifact = EthPMContractInstance(
            address=contract.address,
            block=block_hash,
            contractType=contract_type_str,
            transaction=cast(HexStr, contract.txn_hash),
            runtimeBytecode=contract.contract_type.runtime_bytecode,
        )

        if not (block_0_hash := self.provider.get_block(0).hash):
            raise ProjectError("Chain missing hash for block 0 (required for BIP-122 chain ID).")

        bip122_chain_id = f"{block_0_hash.hex()[2:]}"
        deployments_folder = self.cache_folder / bip122_chain_id
        deployments_folder.mkdir(exist_ok=True, parents=True)
        destination = deployments_folder / f"{contract_name}.json"

        if destination.is_file():
            logger.debug("Deployment already tracked. Re-tracking.")
            # NOTE: missing_ok=True to handle race condition.
            destination.unlink(missing_ok=True)

        destination.write_text(artifact.model_dump_json())

    def __iter__(self) -> Iterator[EthPMContractInstance]:
        """
        Get project deployments.

        Returns:
            Iterator[ethpm_types.ContractInstance]
        """
        if not self.cache_folder.is_dir():
            return

        for ecosystem_path in self.cache_folder.iterdir():
            if not ecosystem_path.is_dir():
                continue

            for deployment in ecosystem_path.iterdir():
                if not self._is_deployment(deployment):
                    continue

                yield EthPMContractInstance.model_validate_json(deployment.read_text())

    def _is_deployment(self, path: Path) -> bool:
        return (
            path.is_file()
            and get_full_extension(path) == ".json"
            and path.stem in (self.project.manifest.contract_types or {})
        )


class LocalProject(Project):
    """
    Manage project(s).

    Usage example::

        from ape import project, Project

        # Interact with local project contracts.
        project.MyToken.deploy(sender=...)

        # Interact with projects located elsewhere.
        other_project = Project("Path/somewhere/else")
        other_project.TokenSwapper.deploy(sender=...)

    """

    def __init__(
        self,
        path: Union[Path, str],
        manifest_path: Optional[Path] = None,
        config_override: Optional[dict] = None,
    ) -> None:
        # A local project uses a special manifest.
        self.path = Path(path).resolve()
        self.manifest_path = manifest_path or self.path / ".build" / "__local__.json"
        manifest = self.load_manifest()

        # NOTE: Set this before super() because needed for self.config read.
        self._config_override = config_override or {}

        super().__init__(manifest, config_override=self._config_override)

        # NOTE: Avoid pointlessly adding info to the __local__ manifest.
        # This is mainly for dependencies.
        if self.manifest_path.stem != "__local__" and not self.manifest.sources:
            # Perform initial manifest updates.
            data: dict = {}
            if (
                self.name
                and self.version
                and (self.version != self.manifest.version or self.name != self.manifest.name)
            ):
                # Ensure name / version is in the manifest correctly.
                data["name"] = self.name.lower().replace("_", "-")
                data["version"] = self.version

            try:
                src_dict = dict(self.sources)
            except Exception as err:
                logger.error(str(err))
            else:
                if src_dict and not self.manifest.sources:
                    # Sources file can be added.
                    # NOTE: Is also updated after compile changes and
                    #   before publishing.
                    data["sources"] = src_dict

            if data:
                self.update_manifest(**data)

    @log_instead_of_fail(default="<ProjectManager>")
    def __repr__(self):
        path = f" {clean_path(self.path)}"
        # NOTE: 'Project' is meta for 'ProjectManager' (mixin magic).
        return f"<ProjectManager{path}>"

    def __contains__(self, name: str) -> bool:
        return name in dir(self) or name in self.contracts

    @property
    def _contract_sources(self) -> list[ContractSource]:
        sources = []
        for contract in self.contracts.values():
            if contract_src := self._create_contract_source(contract.contract_type):
                sources.append(contract_src)

        return sources

    @cached_property
    def _deduced_contracts_folder(self) -> Path:
        # NOTE: This helper is only called if not configured and not ordinary.

        if not self.path.is_dir():
            # Not even able to try.
            return self.path

        common_names = ("contracts", "sources", "src")
        for name in common_names:
            if (self.path / name).is_dir():
                return self.path / name

        # Search for non-JSON contract sources.
        exts_not_json = {
            k for k in self.compiler_manager.registered_compilers.keys() if k != ".json"
        }
        if not exts_not_json:
            # Not really able to look anywhere else.
            return self.path

        attempts = 0
        max_attemps = 20
        for sub_directory in self.path.iterdir():
            if not sub_directory.is_dir():
                continue

            if directory := _find_directory_with_extension(self.path, exts_not_json):
                return directory

            attempts += 1
            if attempts == max_attemps:
                # Project likely does not even have contracts.
                return self.path

        return self.path

    @cached_property
    def project_api(self) -> ProjectAPI:
        """
        The 'type' of project this is, such as an Ape project
        or a Brownie project (or something else).
        """
        project_classes: list[type[ProjectAPI]] = [
            t[1] for t in list(self.plugin_manager.projects)  # type: ignore
        ]
        plugins = [t for t in project_classes if not issubclass(t, ApeProject)]
        for api in plugins:
            if instance := api.attempt_validate(path=self.path):
                return instance

        # Try 'ApeProject' last, in case there was a more specific one earlier.
        if instance := ApeProject.attempt_validate(path=self.path):
            return instance

        raise ProjectError(f"'{self.path.name}' is not recognized as a project.")

    @property
    def name(self) -> str:
        if name := self.config.get("name"):
            return name
        elif name := self.manifest.name:
            return name

        return self.path.name.replace("_", "-").lower()

    @cached_property
    def config(self) -> ApeConfig:
        """
        The project configuration (including global defaults).
        """
        # NOTE: Accessing the config this way allows us
        #  to be a different project than the cwd project.
        project_config = self.project_api.extract_config(**self._config_override)
        return self.config_manager.merge_with_global(project_config)

    @cached_property
    def contracts(self) -> ContractManager:  # type: ignore[override]
        """
        Container for managing contracts from local sources.
        """
        return ContractManager(self, self.sources)

    @property
    def contracts_folder(self) -> Path:
        """
        The root contract source directory.
        """
        if sub_path := self.config.contracts_folder:
            return self.path / sub_path

        return self._deduced_contracts_folder

    @cached_property
    def deployments(self) -> DeploymentManager:
        """
        Project deployment manager for adding and reading
        deployments.
        """
        return DeploymentManager(self)

    @property
    def exclusions(self) -> set[str]:
        """
        Source-file exclusion glob patterns.
        """
        return {*self.config.compile.exclude, *SOURCE_EXCLUDE_PATTERNS}

    @cached_property
    def interfaces_folder(self) -> Path:
        """
        The root interface source directory.
        """
        name = self.config.interfaces_folder
        for base in (self.path, self.contracts_folder):
            path = base / name
            if path.is_dir():
                return path

        # Defaults to non-existing path / interfaces
        return self.path / name

    @property
    def in_tempdir(self) -> bool:
        """
        ``True`` when this project is in the temporary directory,
        meaning existing only in the temporary directory
        namespace.
        """
        if not self.path:
            return False

        temp_dir = os.path.normpath(f"{Path(tempfile.gettempdir()).resolve()}")
        normalized_path = os.path.normpath(self.path)
        return normalized_path.startswith(temp_dir)

    @property
    def manifest(self) -> PackageManifest:
        # Reloads to handle changes from other ongoing sessions.
        # If don't need a reload, use `._manifest` instead.
        if self.manifest_path.is_file():
            reloaded = PackageManifest.model_validate_json(self.manifest_path.read_text())
            self._manifest = reloaded

        return self._manifest

    @property
    def meta(self) -> PackageMeta:
        """
        Metadata about the active project as per EIP
        https://eips.ethereum.org/EIPS/eip-2678#the-package-meta-object
        Use when publishing your package manifest.
        """
        return self.config.meta

    @property
    def scripts_folder(self) -> Path:
        return self.path / "scripts"

    @property
    def sources(self) -> SourceManager:
        """
        All the sources in the project.
        """
        return SourceManager(
            self.path, lambda: self.contracts_folder, exclude_globs=self.exclusions
        )

    @property
    def tests_folder(self) -> Path:
        return self.path / "tests"

    @contextmanager
    def isolate_in_tempdir(self, **config_override) -> Iterator["LocalProject"]:
        """
        Clone this project to a temporary directory and return
        its project.
        """
        if self.in_tempdir:
            # Already in a tempdir.
            if config_override:
                self.reconfigure(**config_override)

            yield self

        else:
            # Add sources to manifest memory, in case they are missing.
            self._manifest.sources = dict(self.sources.items())
            with super().isolate_in_tempdir(**config_override) as project:
                yield project

    def unpack(self, destination: Path, config_override: Optional[dict] = None) -> "LocalProject":
        project = super().unpack(destination, config_override=config_override)

        # Unpack scripts folder.
        if self.scripts_folder.is_dir():
            scripts_destination = destination / "scripts"
            shutil.copytree(self.scripts_folder, scripts_destination, dirs_exist_ok=True)

        # Unpack tests folder.
        if self.tests_folder.is_dir():
            tests_destination = destination / "tests"
            shutil.copytree(self.tests_folder, tests_destination, dirs_exist_ok=True)

        # Unpack interfaces folder.
        if self.interfaces_folder.is_dir():
            prefix = get_relative_path(self.interfaces_folder, self.path)
            interfaces_destination = destination / prefix / self.config.interfaces_folder
            interfaces_destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copytree(self.interfaces_folder, interfaces_destination, dirs_exist_ok=True)

        return project

    def load_manifest(self) -> PackageManifest:
        """
        Load a publish-able manifest.

        Returns:
            ethpm_types.PackageManifest
        """

        if not self.manifest_path.is_file():
            return PackageManifest()

        try:
            return load_manifest(self.manifest_path)
        except Exception as err:
            logger.error(f"__local__.json manifest corrupted! Re-building.\nFull error: {err}.")
            self.manifest_path.unlink(missing_ok=True)
            return PackageManifest()

    def get_contract(self, name: str) -> Any:
        if name in dir(self):
            return self.__getattribute__(name)

        elif contract := self.contracts.get(name):
            contract.base_path = self.path
            return contract

        return None

    def update_manifest(self, **kwargs):
        # Update the manifest in memory.
        super().update_manifest(**kwargs)
        # Write updates to disk.
        self.manifest_path.unlink(missing_ok=True)
        manifest_text = self.manifest.model_dump_json(mode="json", by_alias=True)
        self.manifest_path.parent.mkdir(parents=True, exist_ok=True)
        self.manifest_path.write_text(manifest_text)

    def load_contracts(
        self, *source_ids: Union[Path, str], use_cache: bool = True
    ) -> dict[str, ContractContainer]:
        paths = (
            [(self.path / src_id) for src_id in source_ids] if source_ids else self.sources.paths
        )
        return {
            c.contract_type.name: c
            for c in self.contracts.compile(paths, use_cache=use_cache)
            if c.contract_type.name
        }

    def extract_manifest(self) -> PackageManifest:
        """
        Get a finalized manifest for publishing.

        Returns:
            PackageManifest
        """

        sources = dict(self.sources)
        contract_types = {
            n: ct
            for n, ct in (self.manifest.contract_types or {}).items()
            if ct.source_id in sources
        }

        # Add any remaining data to the manifest here.
        self.update_manifest(
            contract_types=contract_types,
            dependencies=self.dependencies.uri_map,
            deployments=self.deployments.instance_map,
            meta=self.meta,
            name=self.name,
            sources=sources,
            version=self.version,
        )

        return self.manifest

    def clean(self):
        if self.manifest_path.name == "__local__.json":
            self.manifest_path.unlink(missing_ok=True)

    def _create_contract_source(self, contract_type: ContractType) -> Optional[ContractSource]:
        if not (source_id := contract_type.source_id):
            return None

        elif not (src := self.sources.get(source_id)):
            # Not found in this project's sources.
            try:
                cwd = Path.cwd()
            except Exception:
                # Happens when left in a cleaned-up temp path maybe?
                cwd = None

            if cwd is not None and self.path != cwd:
                root_project = self.Project(cwd)
                if src := root_project._create_contract_source(contract_type):
                    return src

            return None

        try:
            return ContractSource.create(contract_type, src, self.path)
        except (ValueError, FileNotFoundError):
            return None

    def _update_contract_types(self, contract_types: dict[str, ContractType]):
        super()._update_contract_types(contract_types)

        if "ABI" in [x.value for x in self.config.compile.output_extra]:
            abi_folder = self.manifest_path.parent / "abi"
            shutil.rmtree(abi_folder, ignore_errors=True)
            abi_folder.mkdir(parents=True, exist_ok=True)
            for name, ct in (self.manifest.contract_types or {}).items():
                file = abi_folder / f"{name}.json"
                abi_json = json.dumps(
                    [x.model_dump_json(by_alias=True, mode="json") for x in ct.abi]
                )
                file.write_text(abi_json)


def _find_directory_with_extension(path: Path, extensions: set[str]) -> Optional[Path]:
    if not path.is_dir():
        return None

    for file in path.iterdir():
        if file.is_file() and get_full_extension(file) in extensions:
            return file.parent

        elif file.is_dir():
            return _find_directory_with_extension(file, extensions)

    return None
