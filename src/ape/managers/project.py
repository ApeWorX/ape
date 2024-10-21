import json
import random
import shutil
from collections.abc import Callable, Iterable, Iterator
from contextlib import contextmanager
from functools import cached_property, singledispatchmethod
from pathlib import Path
from re import Pattern
from typing import Any, Optional, Union, cast

from eth_typing import HexStr
from eth_utils import to_hex
from ethpm_types import ContractInstance as EthPMContractInstance
from ethpm_types import ContractType, PackageManifest, PackageMeta, Source
from ethpm_types.source import Compiler, ContractSource
from ethpm_types.utils import compute_checksum
from pydantic_core import Url

from ape.api.projects import ApeProject, DependencyAPI, ProjectAPI
from ape.contracts import ContractContainer, ContractInstance
from ape.exceptions import APINotImplementedError, ChainError, CompilerError, ProjectError
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
    get_package_path,
    get_relative_path,
    in_tempdir,
    path_match,
)


def _path_to_source_id(path: Path, root_path: Path) -> str:
    return f"{get_relative_path(path.absolute(), root_path.absolute())}"


class SourceManager(BaseManager):
    """
    A manager of a local-project's sources-paths.
    Access via ``project.sources``. Allows source-access
    from both ``source_id`` as well as ``path``. Handles
    detecting modified sources as well as excluded sources.
    Is meant to resemble a PackageManifest's source dict
    but with more functionality for active development.
    """

    _path_cache: Optional[list[Path]] = None

    # perf: calculating paths from source Ids can be expensive.
    _path_to_source_id: dict[Path, str] = {}

    def __init__(
        self,
        root_path: Path,
        get_contracts_path: Callable,
        exclude_globs: Optional[set[Union[str, Pattern]]] = None,
    ):
        self.root_path = root_path
        self.get_contracts_path = get_contracts_path
        self.exclude_globs = exclude_globs or set()
        self._sources: dict[str, Source] = {}
        self._exclude_cache: dict[str, bool] = {}

    @log_instead_of_fail(default="<LocalSources>")
    def __repr__(self) -> str:
        path_str = f" {clean_path(self.get_contracts_path())}"
        return f"<LocalSources{path_str}>"

    def __len__(self) -> int:
        if self._path_cache is not None:
            return len(self._path_cache)

        # Will set _path_cache, eliminates need to iterate (perf).
        return len(list(self.paths))

    def __iter__(self) -> Iterator[str]:
        for path in self.paths:
            yield self._get_source_id(path)

    def __getitem__(self, source_id: str) -> Source:
        src = self.get(source_id)

        # NOTE: Can't use walrus operator here because empty Source objects
        #   are false-y.
        if src is None:
            raise KeyError(f"Source '{source_id}' not found.")

        return src

    def get(self, source_id: str) -> Optional[Source]:
        """
        Get a Source by source_id.

        Args:
            source_id (str): The source identifier.

        Returns:
            Source | None
        """
        if source_id in self._sources:
            return self._sources[source_id]

        for path in self.paths:
            if self._get_source_id(path) == source_id:
                text: Union[str, dict]
                if path.is_file():
                    try:
                        text = path.read_text(encoding="utf8")
                    except Exception:
                        continue

                else:
                    text = {}

                src = Source.model_validate(text)
                self._sources[source_id] = src
                return src

        return None

    def items(self) -> Iterator[tuple[str, Source]]:
        for source_id in self.keys():
            yield source_id, self[source_id]

    def keys(self) -> Iterator[str]:
        for path in self.paths:
            yield self._get_source_id(path)

    def values(self) -> Iterator[Source]:
        for source_id in self.keys():
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

    @cached_property
    def _all_files(self) -> list[Path]:
        try:
            contracts_folder = self.get_contracts_path()
        except ProjectError:
            # No contracts folder found. Might not be in a project.
            return []

        return get_all_files_in_directory(contracts_folder, max_files=500)

    @property
    def paths(self) -> Iterator[Path]:
        """
        All contract sources paths.
        """
        for path in self._all_files:
            if self.is_excluded(path):
                continue

            yield path

    def is_excluded(self, path: Path) -> bool:
        """
        Check if the given path is considered an "excluded"
        file based on the configured ignore-patterns.

        Args:
            path (Path): The path to check.

        Returns:
            bool
        """
        source_id = self._get_source_id(path)
        if source_id in self._exclude_cache:
            return self._exclude_cache[source_id]

        # Non-files and hidden files are ignored.
        is_file = path.is_file()
        if not is_file or path.name.startswith("."):
            # Ignore random hidden files if they are known source types.
            self._exclude_cache[source_id] = True
            return True

        # Files with missing compiler extensions are also ignored.
        suffix = get_full_extension(path)
        registered = self.compiler_manager.registered_compilers
        if suffix not in registered:
            self._exclude_cache[source_id] = True
            return True

        # If we get here, we have a matching compiler and this source exists.
        # Check if is excluded.
        source_id = self._get_source_id(path)
        options = (str(path), path.name, source_id)
        parent_dir_name = path.parent.name

        for excl in self.exclude_globs:
            if isinstance(excl, Pattern):
                for opt in options:
                    if not excl.match(opt):
                        continue

                    self._exclude_cache[source_id] = True
                    return True

            else:
                # perf: Check parent directory first to exclude faster by marking them all.
                if path_match(parent_dir_name, excl):
                    self._exclude_cache[source_id] = True
                    for sub in get_all_files_in_directory(path.parent):
                        sub_source_id = self._get_source_id(sub)
                        self._exclude_cache[sub_source_id] = True

                    return True

                for opt in options:
                    if path_match(opt, excl):
                        self._exclude_cache[source_id] = True
                        return True

        self._exclude_cache[source_id] = False
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

                        # Check exact match w/o extension.
                        prefix = str(file.with_suffix("")).strip(" /\\")
                        if str(full_path).strip(" /\\") == prefix:
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

    def refresh(self):
        """
        Reset file-caches to handle session-changes.
        (Typically not needed to be called by users).
        """
        (self.__dict__ or {}).pop("_all_files", None)
        self._path_to_source_id = {}
        self._path_cache = None

    def _get_source_id(self, path: Path) -> str:
        if src_id := self._path_to_source_id.get(path):
            return src_id

        # Cache because this can be expensive.
        src_id = _path_to_source_id(path, self.root_path)
        self._path_to_source_id[path] = src_id
        return src_id

    def _get_path(self, source_id: str) -> Path:
        return self.root_path / source_id


class ContractManager(BaseManager):
    """
    Local contract-type loader. Only dict-like behavior is public.
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

        raise KeyError(f"Contract '{contract_name}' not found.")

    def __iter__(self) -> Iterator[str]:
        self._compile_missing_contracts(self.sources.paths)
        if contract_types := self.project.manifest.contract_types:
            for ct in contract_types.values():
                if not ct.name or not ct.source_id:
                    continue

                # Ensure was not deleted.
                elif not (self.project.path / ct.source_id).is_file():
                    continue

                yield ct.name

    def get(
        self, name: str, compile_missing: bool = True, check_for_changes: bool = True
    ) -> Optional[ContractContainer]:
        """
        Get a contract by name.

        Args:
            name (str): The name of the contract.
            compile_missing (bool): Set to ``False`` to not attempt compiling
              if the contract can't be found. Note: modified sources are
              re-compiled regardless of this flag.
            check_for_changes (bool): Set to ``False`` if avoiding checking
              for changes.

        Returns:
            ContractContainer | None
        """
        existing_types = self.project.manifest.contract_types or {}
        contract_type = existing_types.get(name)

        if not contract_type:
            if compile_missing:
                self._compile_missing_contracts(self.sources.paths)
                return self.get(name, compile_missing=False)

            return None

        source_id = contract_type.source_id or ""
        source_found = source_id in self.sources

        if not check_for_changes and source_found:
            return ContractContainer(contract_type)

        ext = get_full_extension(source_id)
        if ext not in self.compiler_manager.registered_compilers:
            return ContractContainer(contract_type)

        if source_found:
            if check_for_changes and self._detect_change(source_id):
                compiled = {
                    ct.name: ct
                    for ct in self.compiler_manager.compile(source_id, project=self.project)
                    if ct.name
                }
                if compiled:
                    self.project._update_contract_types(compiled)
                    if name in compiled:
                        return ContractContainer(compiled[name])

            return ContractContainer(contract_type)

        if compile_missing:
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
            if self._detect_change(path):
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

    def _load_contracts(self, use_cache: bool = True) -> dict[str, ContractContainer]:
        return {
            c.contract_type.name: c
            for c in self._compile_all(use_cache=use_cache)
            if c.contract_type.name
        }

    def _compile_all(self, use_cache: bool = True) -> Iterator[ContractContainer]:
        if sources := self.sources:
            paths = sources.paths
            yield from self._compile(paths, use_cache=use_cache)

    def _compile(
        self, paths: Union[Path, str, Iterable[Union[Path, str]]], use_cache: bool = True
    ) -> Iterator[ContractContainer]:
        path_ls = list([paths] if isinstance(paths, (Path, str)) else paths)
        if not path_ls:
            return

        path_ls_final = []
        for path in path_ls:
            path = Path(path)
            if path.is_file() and path.is_absolute():
                path_ls_final.append(path)
            elif (self.project.path / path).is_file():
                path_ls_final.append(self.project.path / path)
            # else: is no longer a file (deleted).

        # Compile necessary contracts.
        if needs_compile := list(
            self._get_needs_compile(path_ls_final) if use_cache else path_ls_final
        ):
            self._compile_contracts(needs_compile)

        src_ids = [
            f"{get_relative_path(Path(p).absolute(), self.project.path)}" for p in path_ls_final
        ]
        for contract_type in (self.project.manifest.contract_types or {}).values():
            if contract_type.source_id and contract_type.source_id in src_ids:
                yield ContractContainer(contract_type)

    def _detect_change(self, path: Union[Path, str]) -> bool:
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

        elif not path.is_file():
            return False  # No longer exists.

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
        self.base_project = project or self.local_project
        # When installed (and set, lazily), this is the dependency project.
        self._installation: Optional["ProjectManager"] = None
        self._tried_fetch = False

    @log_instead_of_fail(default="<Dependency>")
    def __repr__(self) -> str:
        pkg_id = self.package_id

        # Handle local dependencies better.
        path = Path(pkg_id)
        if path.exists():
            pkg_id = clean_path(Path(pkg_id))

        return f"<Dependency package={pkg_id} version={self.api.version_id}>"

    def __hash__(self):
        return hash(f"{self.package_id}@{self.version}")

    @only_raise_attribute_error
    def __getattr__(self, name: str) -> Any:
        return get_attribute_with_extras(self, name)

    def __ape_extra_attributes__(self) -> Iterator[ExtraModelAttributes]:
        yield ExtraModelAttributes(name="project", attributes=lambda: self.project)

    def __eq__(self, other: Any) -> bool:
        if not isinstance(other, Dependency):
            # We can't handle this type.
            # This line causes python to retry from the other end.
            return NotImplemented

        return self.package_id == other.package_id and self.version == other.version

    @property
    def name(self) -> str:
        """
        The short-name of the dependency, used for remappings.
        """
        return self.api.name

    @property
    def package_id(self) -> str:
        """
        The long-name of the dependency, used as an ID.
        """
        return self.api.package_id

    @property
    def version(self) -> str:
        """
        The version of the dependency. Combined with the
        package_id, you have a full identifier of the package.
        """
        return self.api.version_id

    @property
    def project(self) -> "ProjectManager":
        """
        The "project" of the dependency, use like any other
        project in Ape (compile and interact with its contracts).
        """
        return self.install()

    @property
    def _cache(self) -> "PackagesCache":
        return self.base_project.dependencies.packages_cache

    @property
    def project_path(self) -> Path:
        """
        The path to the dependency's project root. When installing, this
        is where the project files go.
        """
        return self._cache.get_project_path(self.package_id, self.version)

    @property
    def manifest_path(self) -> Path:
        """
        The path to the dependency's manifest. When compiling, the artifacts go here.
        """
        return self._cache.get_manifest_path(self.package_id, self.version)

    @property
    def api_path(self) -> Path:
        """
        The path to the dependency's API data-file. This data is necessary
        for managing the install of the dependency.
        """
        return self._cache.get_api_path(self.package_id, self.version)

    @property
    def installed(self) -> bool:
        """
        ``True`` when a project is available. Note: Installed does not mean
        the dependency is compiled!
        """
        if self._installation is not None:
            return True

        elif self.project_path.is_dir():
            if any(x for x in self.project_path.iterdir() if not x.name.startswith(".")):
                return True

        return False

    @property
    def uri(self) -> str:
        """
        The dependency's URI for refreshing.
        """
        return self.api.uri

    def install(
        self, use_cache: bool = True, config_override: Optional[dict] = None
    ) -> "ProjectManager":
        """
        Install this dependency.

        Args:
            use_cache (bool): To force a re-install, like a refresh, set this
              to ``False``.
            config_override (dict): Optionally change the configuration during install.

        Returns:
            :class:`~ape.managers.project.ProjectManager`: The resulting project, ready
            for compiling.
        """
        config_override = {**(self.api.config_override or {}), **(config_override or {})}
        project = None
        did_fetch = False
        if self._installation is not None and use_cache:
            if config_override:
                self._installation.reconfigure(**config_override)

            return self._installation

        elif (
            not self.project_path.is_dir()
            or len([x for x in self.project_path.iterdir() if not x.name.startswith(".")]) == 0
            or not use_cache
        ):
            unpacked = False
            if use_cache and self.manifest_path.is_file():
                # Attempt using sources from manifest. This may happen
                # if having deleted dependencies but not their manifests.
                man = PackageManifest.model_validate_json(self.manifest_path.read_text())
                if man.sources:
                    self.project_path.mkdir(parents=True, exist_ok=True)
                    man.unpack_sources(self.project_path)
                    unpacked = True

            # Either never fetched, it is missing but present in manifest, or we are forcing.
            if not unpacked and not self._tried_fetch:
                logger.debug(f"Fetching {self.api.package_id} {self.api.version_id}")
                # No sources found! Fetch the project.
                shutil.rmtree(self.project_path, ignore_errors=True)
                self.project_path.parent.mkdir(parents=True, exist_ok=True)
                self._tried_fetch = True

                try:
                    self.api.fetch(self.project_path)
                except Exception as err:
                    raise ProjectError(f"Fetching failed: {err}")

                did_fetch = True

                # Reset global tried-fetch if it succeeded, so it can refresh
                # if needbe.
                self._tried_fetch = False

        # Set name / version for the project, if it needs.
        if "name" not in config_override:
            config_override["name"] = self.api.name
        if "version" not in config_override:
            config_override["version"] = self.api.version_id

        if self.project_path.is_dir():
            paths = get_all_files_in_directory(self.project_path)

            # Check if given only a manifest.
            if len(paths) == 1:
                suffix = get_full_extension(paths[0])
                if suffix == ".json":
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
            raise ProjectError("Project install failed.")

        # Cache for next time.
        self._installation = project

        # Also, install dependencies of dependencies, if fetching for the
        # first time.
        if did_fetch:
            spec = project.dependencies.get_project_dependencies(use_cache=use_cache)
            list(spec)

        return project

    def uninstall(self):
        self._cache.remove(self.package_id, self.version)
        self._installation = None

    def compile(
        self, use_cache: bool = True, config_override: Optional[dict] = None
    ) -> dict[str, ContractContainer]:
        """
        Compile a dependency.

        Args:
            use_cache (bool): Set to ``False`` to force a re-compile.
            config_override (Optional[dict]): Optionally override the configuration,
              which may be needed for compiling.

        Returns:
            dict[str, :class:`~ape.contracts.ContractContainer`]
        """
        override = {**self.api.config_override, **(config_override or {})}
        self.api.config_override = override
        project = self.project
        if override:
            # Ensure is using most up-to-date config override.
            project.reconfigure(**override)
            self._cache.cache_api(self.api)

        result = project.load_contracts(use_cache=use_cache)
        if not result:
            contracts_folder = project.contracts_folder
            message = "Compiling dependency produced no contract types."
            if isinstance(project, LocalProject):
                all_files = [x.name for x in get_all_files_in_directory(contracts_folder)]
                has_solidity_sources = any(get_full_extension(Path(x)) == ".sol" for x in all_files)
                has_vyper_sources = any(
                    get_full_extension(Path(x)) in (".vy", ".vyi") for x in all_files
                )
                compilers = self.compiler_manager.registered_compilers
                warn_sol = has_solidity_sources and ".sol" not in compilers
                warn_vyper = has_vyper_sources and ".vy" not in compilers
                suffix = ""
                if warn_sol:
                    suffix = "Try installing 'ape-solidity'"
                    if warn_vyper:
                        suffix += " or 'ape-vyper'"
                elif warn_vyper:
                    suffix = "Try installing 'ape-vyper'"

                elif len(all_files) == 0:
                    suffix = (
                        f"No source files found! (contracts_folder={clean_path(contracts_folder)})"
                    )

                if suffix:
                    message = f"{message} {suffix}."

            logger.warning(message)

        return result

    def unpack(self, path: Path) -> Iterator["Dependency"]:
        """
        Move dependencies into a .cache folder. Also unpacks
        dependencies of dependencies. Ideal for tmp-projects.

        Args:
            path (Path): The destination where to unpack sources.

        Returns:
            Iterates over every dependency unpacked, so the user
            knows the dependencies of dependencies.
        """
        yield from self._unpack(path, set())

    def _unpack(self, path: Path, tracked: set[str]) -> Iterator["Dependency"]:
        key = self.package_id
        if key in tracked:
            return

        tracked.add(key)

        # NOTE: Don't do the same weird path-ify thing for
        #  the in-contracts .cache folder. Short names work here.
        folder = path / self.name / self.version

        if not folder.is_dir():
            # Not yet unpacked.
            if isinstance(self.project, LocalProject):
                contracts_folder_id = get_relative_path(
                    self.project.contracts_folder, self.project.path
                )
                destination = folder / contracts_folder_id
                destination.parent.mkdir(parents=True, exist_ok=True)
                if self.project.contracts_folder.is_dir():
                    shutil.copytree(self.project.contracts_folder, destination)

            else:
                # Will create contracts folder from source IDs.
                folder.parent.mkdir(parents=True, exist_ok=True)
                self.project.manifest.unpack_sources(folder)

        # self is done!
        yield self

        # Unpack dependencies of dependencies (if they aren't already).
        for dependency in self.project.dependencies.specified:
            for unpacked_dep in dependency._unpack(path, tracked=tracked):
                yield unpacked_dep


def _get_cache_versions_suffix(package_id) -> Path:
    package_id_name = package_id.replace("/", "_")
    return Path(package_id_name)


def _get_cache_suffix(package_id: str, version: str, suffix: str = "") -> Path:
    package_id_path = _get_cache_versions_suffix(package_id)
    version_name = f"{version.replace('.', '_').replace('/', '_')}{suffix}"
    return package_id_path / version_name


def _get_cache_path(
    base_path: Path, package_id: str, version: str, is_dir: bool = False, suffix: str = ""
) -> Path:
    options = _version_to_options(version)
    original = None
    for option in options:
        path = base_path / _get_cache_suffix(package_id, option, suffix=suffix)

        if original is None:
            # The 'original' is the first option.
            original = path

        if (is_dir and path.is_dir()) or (not is_dir and path.is_file()):
            return path

    # Return original - may no be created yet!
    assert original is not None  # For mypy.
    return original


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

    def get_project_versions_path(self, package_id: str) -> Path:
        """
        The path to all the versions (projects) of a dependency.
        """
        return self.projects_folder / _get_cache_versions_suffix(package_id)

    def get_project_path(self, package_id: str, version: str) -> Path:
        """
        Path to the dir of the cached project.
        """
        return _get_cache_path(self.projects_folder, package_id, version, is_dir=True)

    def get_manifest_path(self, package_id: str, version: str) -> Path:
        """
        Path to the manifest filepath the dependency project uses
        as a base.
        """
        return _get_cache_path(self.manifests_folder, package_id, version, suffix=".json")

    def get_api_path(self, package_id: str, version: str) -> Path:
        """
        Path to the manifest filepath the dependency project uses
        as a base.
        """
        return _get_cache_path(self.api_folder, package_id, version, suffix=".json")

    def cache_api(self, api: DependencyAPI) -> Path:
        """
        Cache a dependency JSON for usage outside of the project.
        """
        api_file = self.get_api_path(api.package_id, api.version_id)
        api_file.parent.mkdir(parents=True, exist_ok=True)
        api_file.unlink(missing_ok=True)

        # NOTE: All the excludes only for sabing disk space.
        json_text = api.model_dump_json(
            by_alias=True,
            mode="json",
            exclude_none=True,
            exclude_unset=True,
            exclude_defaults=True,
        )

        api_file.write_text(json_text, encoding="utf8")
        return api_file

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

        api_file = self.get_api_path(package_id, version)
        api_file.unlink(missing_ok=True)
        manifest_file = self.get_manifest_path(package_id, version)
        manifest_file.unlink(missing_ok=True)


def _version_to_options(version: str) -> tuple[str, ...]:
    if version.startswith("v"):
        # with the v, without
        return (version, version[1:])

    elif version and version[0].isnumeric():
        # without the v, and with.
        return (version, f"v{version}")

    return (version,)


class DependencyVersionMap(dict[str, "ProjectManager"]):
    """
    A mapping of versions to dependencies.
    This class exists to allow both v-prefixed versions
    as well none v-prefixed versions.
    """

    def __init__(self, name: str):
        self._name = name

    @log_instead_of_fail(default="<DependencyVersionMap>")
    def __repr__(self) -> str:
        keys = ",".join(list(self.keys()))
        return f"<{self._name} versions='{keys}'>"

    def __contains__(self, version: Any) -> bool:
        if not isinstance(version, str):
            return False

        options = _version_to_options(version)
        return any(dict.__contains__(self, v) for v in options)  # type: ignore

    def __getitem__(self, version: str) -> "ProjectManager":
        options = _version_to_options(version)
        for vers in options:
            if not dict.__contains__(self, vers):  # type: ignore
                continue

            # Found.
            return dict.__getitem__(self, vers)  # type: ignore

        raise KeyError(version)

    def get(  # type: ignore
        self, version: str, default: Optional["ProjectManager"] = None
    ) -> Optional["ProjectManager"]:
        options = _version_to_options(version)
        for vers in options:
            if not dict.__contains__(self, vers):  # type: ignore
                continue

            # Found.
            return dict.get(self, vers)  # type: ignore

        return default

    def extend(self, data: dict):
        for key, val in data.items():
            self[key] = val


class DependencyManager(BaseManager):
    """
    Manage dependencies for an Ape project.
    Note: Every project gets its own dependency-set (DependencyManager).
    """

    # Class-level cache
    _cache: dict[DependencyAPI, Dependency] = {}

    def __init__(self, project: Optional["ProjectManager"] = None):
        self.project = project or self.local_project

    @log_instead_of_fail(default="<DependencyManager>")
    def __repr__(self) -> str:
        result = "<DependencyManager"
        project_id = None
        if hasattr(self.project, "path"):
            project_id = clean_path(self.project.path)
        elif name := self.project.name:
            project_id = name

        return f"{result} project={project_id}>" if project_id else f"{result}>"

    def __iter__(self) -> Iterator[Dependency]:
        yield from self.specified

    def __len__(self) -> int:
        # NOTE: Using the config value keeps use lazy and fast.
        return len(self.project.config.dependencies)

    def __getitem__(self, name: str) -> DependencyVersionMap:
        result = DependencyVersionMap(name)

        # Always ensure the specified are included, even if not yet installed.
        if versions := {d.version: d.project for d in self.get_project_dependencies(name=name)}:
            result.extend(versions)

        # Add remaining installed versions.
        for dependency in self.get_versions(name):
            if dependency.version not in result:
                result[dependency.version] = dependency.project

        return result

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
            if isinstance(config_key, tuple):
                for sub_key in config_key:
                    dependency_classes[sub_key] = dependency_class
            else:
                # Single str-given.
                dependency_classes[config_key] = dependency_class

        return dependency_classes

    @property
    def specified(self) -> Iterator[Dependency]:
        """
        All dependencies specified in the config.
        """
        yield from self.get_project_dependencies()

    def get_project_dependencies(
        self,
        use_cache: bool = True,
        config_override: Optional[dict] = None,
        name: Optional[str] = None,
        version: Optional[str] = None,
        allow_install: bool = True,
    ) -> Iterator[Dependency]:
        """
        Get dependencies specified in the project's ``ape-config.yaml`` file.

        Args:
            use_cache (bool): Set to ``False`` to force-reinstall dependencies.
               Defaults to ``True``. Does not work with ``allow_install=False``.
            config_override (Optional[dict]): Override shared configuration for each dependency.
            name (Optional[str]): Optionally only get dependencies with a certain name.
            version (Optional[str]): Optionally only get dependencies with certain version.
            allow_install (bool): Set to ``False`` to not allow installing uninstalled
              specified dependencies.

        Returns:
            Iterator[:class:`~ape.managers.project.Dependency`]
        """

        for api in self.config_apis:
            if (name is not None and api.name != name and api.package_id != name) or (
                version is not None and api.version_id != version
            ):
                continue

            # Ensure the dependency API data is known.
            dependency = self.add(api)

            if allow_install:
                try:
                    dependency.install(use_cache=use_cache, config_override=config_override)
                except ProjectError:
                    # This dependency has issues. Let's wait to until the user
                    # actually requests something before failing, and
                    # yield an uninstalled version of the specified dependency for
                    # them to fix.
                    pass

            yield dependency

    @property
    def config_apis(self) -> Iterator[DependencyAPI]:
        for data in self.config.dependencies:
            yield self.decode_dependency(**data)

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
                api = self.decode_dependency(**data)
                if api.name == self.project.name:
                    # Don't include self as a dependency
                    # (happens when compiling a dependency)
                    continue

                yield self._create_dependency(api)

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

        if name_matches:
            return name_matches[0]

        # Was not found in this project's dependencies.
        checked.add(self.project.project_id)

        deps = [*self.installed]
        if allow_install:
            deps.extend([*self.specified])

        # Still not found - check dependencies of dependencies.
        # NOTE: Purposely checking all specified first.
        for dependency in deps:
            try:
                sub_project = dependency.project
            except ProjectError:
                continue

            key = sub_project.project_id
            if key in checked:
                continue

            checked.add(key)
            if sub_dependency := sub_project.dependencies._get(
                name, version, checked=checked, allow_install=allow_install
            ):
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
        for dependency in self.get_project_dependencies(name=name):
            if dependency.version in versions_yielded:
                continue

            yield dependency
            versions_yielded.add(dependency.version)

        # Yield any remaining installed.
        using_package_id = False
        for dependency in self.installed:
            if dependency.package_id != name:
                continue

            using_package_id = True
            if dependency.version in versions_yielded:
                continue

            yield dependency
            versions_yielded.add(dependency.version)

        if using_package_id:
            # Done.
            return

        # Never yield. Check if using short-name.
        for dependency in self.installed:
            if dependency.name != name:
                continue

            elif dependency.version in versions_yielded:
                continue

            yield dependency
            versions_yielded.add(dependency.version)

    def _create_dependency(self, api: DependencyAPI) -> Dependency:
        if api in self._cache:
            return self._cache[api]

        dependency = Dependency(api, project=self.project)
        self._cache[api] = dependency
        return dependency

    def get_dependency(
        self, dependency_id: str, version: str, allow_install: bool = True
    ) -> Dependency:
        """
        Get a dependency.

        Args:
            dependency_id (str): The package ID of the dependency. You can also
              provide the short-name of the dependency.
            version (str): The version identifier.
            allow_install (bool): If the dependendency API is known but the
              project is not installed, attempt to install it. Defaults to ``True``.

        Raises:
            :class:`~ape.exceptions.ProjectError`: When unable to find the
              dependency.

        Returns:
            class:`~ape.managers.project.Dependency`
        """
        version_options = _version_to_options(version)

        # Also try the lower of the name
        # so ``OpenZeppelin`` would give you ``openzeppelin``.
        id_options = [dependency_id]
        if dependency_id.lower() != dependency_id:
            # Ensure we try dependency_id without lower first.
            id_options.append(dependency_id.lower())

        def try_get():
            for dep_id in id_options:
                for v in version_options:
                    # NOTE: `allow_install=False` here because we install
                    # _after_ exhausting all options.
                    if dependency := self._get(dep_id, v, allow_install=False):
                        return dependency

        if res := try_get():
            return res

        if allow_install:
            # Try installing first.
            self.install()

        if res := try_get():
            return res

        raise ProjectError(f"Dependency '{dependency_id}' with version '{version}' not found.")

    def decode_dependency(self, **item: Any) -> DependencyAPI:
        """
        Decode data into a :class:`~ape.api.projects.DependencyAPI`.

        Args:
            **item: The same data you put in your ``dependencies:`` config.

        Raises:
            :class:`~ape.exceptions.ProjectError`: When unable to handle the
              given API data.

        Returns:
            :class:`~ape.api.projects.DependencyAPI`
        """
        for key, cls in self.types.items():
            if key in item:
                return cls.model_validate(item)

        name = item.get("name") or f"{item}"  # NOTE: Using 'or' for short-circuit eval
        raise ProjectError(
            f"No installed dependency API that supports '{name}'. "
            f"Keys={', '.join([x for x in item.keys()])}"
        )

    def add(self, dependency: Union[dict, DependencyAPI]) -> Dependency:
        """
        Add the dependency API data. This sets up a dependency such that
        it can be fetched.

        Args:
            dependency (dict | :class:`~ape.api.projects.DependencyAPI`): The
              API data necessary for fetching the dependency.

        Returns:
            class:`~ape.managers.project.Dependency`
        """

        api = self.decode_dependency(**dependency) if isinstance(dependency, dict) else dependency
        self.packages_cache.cache_api(api)

        # Avoid infinite loop where Ape re-tries installing the dependency
        # again and again in error situations.
        install_if_not_found = False

        try:
            return self.get_dependency(
                api.package_id,
                api.version_id,
                allow_install=install_if_not_found,
            )
        except ProjectError:
            raise  # Avoids bottom except.
        except Exception as err:
            raise ProjectError(
                f"Failed to add dependency {api.name}@{api.version_id}: {err}"
            ) from err

    def install(self, **dependency: Any) -> Union[Dependency, list[Dependency]]:
        """
        Install dependencies.

        Args:
            **dependency: Dependency data, same to what you put in `dependencies:` config.
              When excluded, installs all project-specified dependencies. Also, use
              ``use_cache=False`` to force a re-install.

        Returns:
            :class:`~ape.managers.project.Dependency` when given data else a list
            of them, one for each specified.
        """
        use_cache: bool = dependency.pop("use_cache", True)
        if dependency:
            return self.install_dependency(dependency, use_cache=use_cache)

        # Install all project's.
        result: list[Dependency] = []

        # Log the errors as they happen but don't crash the full install.
        for dep in self.get_project_dependencies(use_cache=use_cache):
            result.append(dep)

        return result

    def install_dependency(
        self,
        dependency_data: Union[dict, DependencyAPI],
        use_cache: bool = True,
        config_override: Optional[dict] = None,
    ) -> Dependency:
        dependency = self.add(dependency_data)
        dependency.install(use_cache=use_cache, config_override=config_override)
        return dependency

    def unpack(self, base_path: Path, cache_name: str = ".cache"):
        """
        Move dependencies into a .cache folder.
        Ideal for isolated, temporary projects.

        Args:
            base_path (Path): The target path.
            cache_name (str): The cache folder name to create
              at the target path. Defaults to ``.cache`` because
              that is what is what ``ape-solidity`` uses.
        """
        cache_folder = base_path / cache_name
        for dependency in self.specified:
            dependency.unpack(cache_folder)


def _load_manifest(path: Union[Path, str]) -> PackageManifest:
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
        config_override = config_override or {}
        manifest = _load_manifest(manifest) if isinstance(manifest, (Path, str)) else manifest
        return Project(manifest, config_override=config_override)

    @classmethod
    def from_python_library(
        cls, package_name: str, config_override: Optional[dict] = None
    ) -> "LocalProject":
        """
        Create an Ape project instance from an installed Python package.
        This is useful for when Ape or Vyper projects are published to
        pypi.

        Args:
            package_name (str): The name of the package's folder that would
              appear in site-packages.
            config_override (dict | None): Optionally override the configuration
              for this project.

        Returns:
            :class:`~ape.managers.project.LocalProject`
        """
        try:
            pkg_path = get_package_path(package_name)
        except ValueError as err:
            raise ProjectError(str(err)) from err

        # Treat site-package as a local-project.
        return LocalProject(pkg_path, config_override=config_override)

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
        return get_attribute_with_extras(self, item)

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

    def __ape_extra_attributes__(self) -> Iterator[ExtraModelAttributes]:
        extras = (
            ExtraModelAttributes(
                name="contracts",
                attributes=lambda: self.contracts,
                include_getitem=True,
            ),
            ExtraModelAttributes(
                name="manifest",
                attributes=lambda: self.manifest,
                include_getitem=True,
                include_getattr=False,  # avoids contract-type confusion.
            ),
        )

        # If manifest is not compiled, don't search for contracts right
        # away to delay compiling if unnecessary.
        yield from extras if self.manifest.contract_types else reversed(extras)

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
            path.write_text(str(src.content), encoding="utf8")

        # Unpack config file.
        # NOTE: Always unpacks into a regular .yaml config file for simplicity
        #   and maximum portibility.
        self.config.write_to_disk(destination / "ape-config.yaml")

        return LocalProject(destination, config_override=config_override)

    def update_manifest(self, **kwargs):
        """
        Change manifest values. Overwrites.

        Args:
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

    @property
    def sources(self) -> dict[str, Source]:
        return self.manifest.sources or {}

    def load_contracts(
        self, *source_ids: Union[str, Path], use_cache: bool = True
    ) -> dict[str, ContractContainer]:
        result = {
            ct.name: ct
            for ct in ((self.manifest.contract_types or {}) if use_cache else {}).values()
            if ct.name
        }
        compiled_source_ids = {ct.source_id for ct in result.values() if ct.source_id}
        source_iter: Iterable = source_ids or list(self.manifest.sources or {})
        source_iter = [f"{x}" for x in source_iter]
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
        contract_types = {**(self._manifest.contract_types or {}), **contract_types}
        sources = dict(self.sources.items())
        self.update_manifest(contract_types=contract_types, sources=sources)

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

        self.account_manager.test_accounts.reset()

    def extract_manifest(self) -> PackageManifest:
        # Attempt to compile, if needed.
        try:
            self.load_contracts()
        except CompilerError as err:
            # Some manifest-based projects may not require compiling,
            # such as OpenZeppelin or snekmate.
            logger.warning(err)

        return self.manifest

    def clean(self):
        self._manifest.contract_types = None
        self._config_override = {}


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

        block_hash = to_hex(block_hash_bytes)
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

        bip122_chain_id = f"{to_hex(block_0_hash)[2:]}"
        deployments_folder = self.cache_folder / bip122_chain_id
        deployments_folder.mkdir(exist_ok=True, parents=True)
        destination = deployments_folder / f"{contract_name}.json"

        if destination.is_file():
            logger.debug("Deployment already tracked. Re-tracking.")
            # NOTE: missing_ok=True to handle race condition.
            destination.unlink(missing_ok=True)

        destination.write_text(artifact.model_dump_json(), encoding="utf8")

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
        self._session_source_change_check: set[str] = set()

        # NOTE: Set this before super() because needed for self.config read.
        self._config_override = config_override or {}

        self._base_path = Path(path).resolve()

        # A local project uses a special manifest.
        self.manifest_path = manifest_path or self._base_path / ".build" / "__local__.json"
        manifest = self.load_manifest()

        super().__init__(manifest, config_override=self._config_override)

        self.path = self._base_path / (self.config.base_path or "")

        # NOTE: Avoid pointlessly adding info to the __local__ manifest.
        # This is mainly for dependencies.
        if self.manifest_path.stem != "__local__" and not manifest.sources:
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
                src_dict = dict(self.sources.items())
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

        # Ensure any custom networks will work, otherwise Ape's network manager
        # only knows about the "local" project's.
        if custom_nets := (config_override or {}).get("networks", {}).get("custom", []):
            self.network_manager._custom_networks.extend(custom_nets)

    @log_instead_of_fail(default="<ProjectManager>")
    def __repr__(self):
        path = f" {clean_path(self._base_path)}"
        # NOTE: 'Project' is meta for 'ProjectManager' (mixin magic).
        return f"<ProjectManager{path}>"

    def __contains__(self, name: str) -> bool:
        return name in dir(self) or name in self.contracts

    @only_raise_attribute_error
    def __getattr__(self, item: str) -> Any:
        try:
            return get_attribute_with_extras(self, item)
        except AttributeError as err:
            message = getattr(err, "message", str(err))
            did_append = False

            if item not in (self.manifest.contract_types or {}):
                all_files = get_all_files_in_directory(self.contracts_folder)
                for path in all_files:
                    # Possibly, the user was trying to use a file name instead.
                    if path.stem != item:
                        continue

                    if message and message[-1] not in (".", "?", "!"):
                        message = f"{message}."

                    message = (
                        f"{message} However, there is a source file named '{path.name}'. "
                        "This file may not be compiling (see error above), or maybe you meant "
                        "to reference a contract name from this source file?"
                    )
                    did_append = True
                    break

                # Possibly, the user does not have compiler plugins installed or working.
                missing_exts = set()
                for path in all_files:
                    if ext := get_full_extension(path):
                        if ext not in self.compiler_manager.registered_compilers:
                            missing_exts.add(ext)

                if missing_exts:
                    start = "Else, could" if did_append else "Could"
                    message = (
                        f"{message} {start} it be from one of the "
                        "missing compilers for extensions: " + f'{", ".join(sorted(missing_exts))}?'
                    )

            err.args = (message,)
            raise  # The same exception (keep the stack the same height).

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

        exts_not_json = {
            k for k in self.compiler_manager.registered_compilers.keys() if k != ".json"
        }
        if not exts_not_json:
            # Not really able to look anywhere else.
            return self.path

        def find_in_subs(pth):
            for sub_directory in pth.iterdir():
                if not sub_directory.is_dir():
                    continue

                if directory := _find_directory_with_extension(sub_directory, exts_not_json):
                    return directory

        if res := find_in_subs(self.path):
            return res

        if _find_directory_with_extension(self.path, exts_not_json, recurse=False):
            return self.path

        # Doesn't exist. Return non-existent default directory.
        return self.path / "contracts"

    @cached_property
    def project_api(self) -> ProjectAPI:
        """
        The 'type' of project this is, such as an Ape project
        or a Brownie project (or something else).
        """
        default_project = self._get_ape_project_api()

        # If an ape-config.yaml file, exists stop now.
        if default_project and default_project.config_file.is_file():
            return default_project

        # ape-config.yaml does no exist. Check for another ProjectAPI type.
        project_classes: list[type[ProjectAPI]] = [
            t[1] for t in list(self.plugin_manager.projects)  # type: ignore
        ]
        plugins = [t for t in project_classes if not issubclass(t, ApeProject)]
        for api in plugins:
            if instance := api.attempt_validate(path=self._base_path):
                return instance

        # If no other APIs worked but we have a default Ape project, use that!
        # It should work in most cases (hopefully!).
        if default_project:
            return default_project

        # For some reason we were just not able to create a project here.
        # I am not sure this is even possible.
        raise ProjectError(f"'{self._base_path.name}' is not recognized as a project.")

    def _get_ape_project_api(self) -> Optional[ApeProject]:
        if instance := ApeProject.attempt_validate(path=self._base_path):
            return cast(ApeProject, instance)

        return None

    @property
    def name(self) -> str:
        if name := self.config.get("name"):
            return name
        elif name := self.manifest.name:
            return name

        return self._base_path.name.replace("_", "-").lower()

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
    def exclusions(self) -> set[Union[str, Pattern]]:
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

        return in_tempdir(self.path)

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

    @cached_property
    def sources(self) -> SourceManager:  # type: ignore[override]
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
        its project.vers_settings["outputSelection"]
        """
        if self.in_tempdir:
            # Already in a tempdir.
            if config_override:
                self.reconfigure(**config_override)

            yield self

        else:
            sources = dict(self.sources.items())
            with super().isolate_in_tempdir(**config_override) as project:
                # Add sources to manifest memory, in case they are missing.
                project.manifest.sources = sources
                yield project

    def unpack(self, destination: Path, config_override: Optional[dict] = None) -> "LocalProject":
        config_override = {**self._config_override, **(config_override or {})}

        # Unpack contracts.
        if self.contracts_folder.is_dir():
            contracts_path = get_relative_path(self.contracts_folder, self.path)
            contracts_destination = destination / contracts_path
            shutil.copytree(self.contracts_folder, contracts_destination, dirs_exist_ok=True)

        # Unpack config file.
        if not (destination / "ape-config.yaml").is_file():
            self.config.write_to_disk(destination / "ape-config.yaml")

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

        return LocalProject(destination, config_override=config_override)

    def load_manifest(self) -> PackageManifest:
        """
        Load a publish-able manifest.

        Returns:
            ethpm_types.PackageManifest
        """

        if not self.manifest_path.is_file():
            return PackageManifest()

        try:
            manifest = _load_manifest(self.manifest_path)
        except Exception as err:
            logger.error(f"__local__.json manifest corrupted! Re-building.\nFull error: {err}.")
            self.manifest_path.unlink(missing_ok=True)
            manifest = PackageManifest()

        self._manifest = manifest
        return manifest

    def get_contract(self, name: str) -> Any:
        if name in self._session_source_change_check:
            check_for_changes = False
        else:
            check_for_changes = True
            self._session_source_change_check.add(name)

        contract = self.contracts.get(name, check_for_changes=check_for_changes)
        if contract:
            contract.base_path = self.path

        return contract

    def update_manifest(self, **kwargs):
        # Update the manifest in memory.
        super().update_manifest(**kwargs)
        # Write updates to disk.
        self.manifest_path.unlink(missing_ok=True)
        manifest_text = self.manifest.model_dump_json(mode="json", by_alias=True)
        self.manifest_path.parent.mkdir(parents=True, exist_ok=True)
        self.manifest_path.write_text(manifest_text, encoding="utf8")

    def load_contracts(
        self, *source_ids: Union[str, Path], use_cache: bool = True
    ) -> dict[str, ContractContainer]:
        paths: Iterable[Path]
        starting: dict[str, ContractContainer] = {}
        if source_ids:
            paths = [(self.path / src_id) for src_id in source_ids]
        else:
            starting = {
                n: ContractContainer(ct)
                for n, ct in (self.manifest.contract_types or {}).items()
                if use_cache and ct.source_id and (self.path / ct.source_id).is_file()
            }
            paths = self.sources.paths

        new_types = {
            c.contract_type.name: c
            for c in self.contracts._compile(paths, use_cache=use_cache)
            if c.contract_type.name
        }
        return {**starting, **new_types}

    def extract_manifest(self) -> PackageManifest:
        """
        Get a finalized manifest for publishing.

        Returns:
            PackageManifest
        """

        sources = dict(self.sources)
        contract_types = {
            n: c.contract_type
            for n, c in self.load_contracts().items()
            if c.contract_type.source_id in sources
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
        super().clean()
        if self.manifest_path.name == "__local__.json":
            self.manifest_path.unlink(missing_ok=True)
            self._manifest = PackageManifest()

        self.sources._path_cache = None
        self._clear_cached_config()

    def reload_config(self):
        """
        Reload the local ape-config.yaml file.
        This is useful if the file was modified in the
        active python session.
        """
        self._clear_cached_config()
        _ = self.config

    def refresh_sources(self):
        """
        Check for file-changes. Typically, you don't need to call this method.
        This method exists for when changing files mid-session, you can "refresh"
        and Ape will know about the changes.
        """
        self._session_source_change_check = set()
        self.sources.refresh()

    def _clear_cached_config(self):
        if "config" in self.__dict__:
            del self.__dict__["config"]

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
                abi_json = json.dumps([x.model_dump(by_alias=True, mode="json") for x in ct.abi])
                file.write_text(abi_json, encoding="utf8")


def _find_directory_with_extension(
    path: Path, extensions: set[str], recurse: bool = True
) -> Optional[Path]:
    if not path.is_dir():
        return None

    for file in path.iterdir():
        if file.is_file() and get_full_extension(file) in extensions:
            return file.parent

        elif recurse and file.is_dir():
            return _find_directory_with_extension(file, extensions)

    return None
