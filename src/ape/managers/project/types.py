import json
from pathlib import Path
from typing import List, Optional

import yaml
from ethpm_types import PackageManifest
from ethpm_types.utils import compute_checksum

from ape.api import ProjectAPI
from ape.logging import logger
from ape.managers.config import CONFIG_FILE_NAME as APE_CONFIG_FILE_NAME
from ape.utils import get_all_files_in_directory, get_relative_path


class BaseProject(ProjectAPI):
    created_temporary_config_file: bool = False

    @property
    def config_file(self) -> Path:
        return self.path / APE_CONFIG_FILE_NAME

    @property
    def is_valid(self) -> bool:
        if self.config_file.exists():
            return True

        logger.warning(
            f"'{self.path.name}' is not an 'ApeProject', but attempting to process as one."
        )

        # NOTE: We always return True as a last-chance attempt because it often
        # works anyway and prevents unnecessary plugin requirements.
        return True

    @property
    def sources(self) -> List[Path]:
        """
        All the source files in the project.
        Excludes files with extensions that don't have a registered compiler.
        Returns:
            List[pathlib.Path]: A list of a source file paths in the project.
        """
        files: List[Path] = []

        if not self.contracts_folder.exists():
            return files

        for extension in self.compiler_manager.registered_compilers:
            r_ext = extension.replace(".", "\\.")
            files.extend(
                get_all_files_in_directory(self.contracts_folder, pattern=rf"[\w|-]+{r_ext}")
            )

        return files

    def configure(self, **kwargs):
        # Don't override existing config file.
        if self.config_file.exists():
            return

        config_data = {**kwargs}
        if self.name:
            config_data["name"] = self.name
        if self.version:
            config_data["version"] = self.version

        contracts_folder_config_item = (
            str(self.contracts_folder).replace(str(self.path), "").strip("/")
        )
        config_data["contracts_folder"] = contracts_folder_config_item
        with open(self.config_file, "w") as f:
            yaml.safe_dump(config_data, f)

            # Indicate that we need to clean up the file later.
            self.created_temporary_config_file = True

    def create_manifest(
        self, file_paths: Optional[List[Path]] = None, use_cache: bool = True
    ) -> PackageManifest:
        # Create a config file if one doesn't exist to forward values from
        # the root project's 'ape-config.yaml' 'dependencies:' config.
        try:
            self.configure()

            # Load a cached or clean manifest (to use for caching)
            if self.cached_manifest and use_cache:
                manifest = self.cached_manifest
            else:
                manifest = PackageManifest()

                if self.manifest_cachefile.exists():
                    self.manifest_cachefile.unlink()

            cached_sources = manifest.sources or {}
            cached_contract_types = manifest.contract_types or {}
            cached_source_reference_paths = {
                source_id: [
                    self.contracts_folder.joinpath(Path(s))
                    for s in getattr(source, "references", []) or []
                ]
                for source_id, source in cached_sources.items()
            }
            source_paths = (
                {p for p in self.sources if p in file_paths} if file_paths else set(self.sources)
            )

            # Filter out deleted source_paths
            deleted_source_ids = cached_sources.keys() - set(
                map(str, [get_relative_path(p, self.contracts_folder) for p in source_paths])
            )
            contract_types = {
                name: contract_type
                for name, contract_type in cached_contract_types.items()
                if contract_type.source_id not in deleted_source_ids
            }

            def does_need_compiling(source_path: Path) -> bool:
                source_id = str(get_relative_path(source_path, self.contracts_folder))

                if source_id not in cached_sources:
                    return True  # New file added

                cached_source = cached_sources[source_id]
                cached_checksum = cached_source.calculate_checksum()

                source_file = self.contracts_folder / source_path
                checksum = compute_checksum(
                    source_file.read_text("utf8").encode("utf8"),
                    algorithm=cached_checksum.algorithm,
                )

                return checksum != cached_checksum.hash  # Contents changed

            # NOTE: Filter by checksum to only update what's needed
            needs_compiling = set(filter(does_need_compiling, source_paths))

            # NOTE: Add referring path imports for each source path
            referenced_paths: List[Path] = []

            paths_to_compile = needs_compiling.copy()

            # NOTE: Recompile all dependent sources for a changed source
            while paths_to_compile:
                source_id = str(get_relative_path(paths_to_compile.pop(), self.contracts_folder))
                ref_paths = cached_source_reference_paths.get(source_id, [])
                referenced_paths.extend(ref_paths)
                paths_to_compile.update(ref_paths)

            needs_compiling.update(referenced_paths)

            # Set the context in case compiling a dependency (or anything outside the root project).
            with self.config_manager.using_project(
                self.path, contracts_folder=self.contracts_folder
            ):
                self.project_manager._load_dependencies()
                compiled_contract_types = self.compiler_manager.compile(list(needs_compiling))
                contract_types.update(compiled_contract_types)

                # NOTE: Update contract types & re-calculate source code entries in manifest
                source_paths = (
                    {p for p in self.sources if p in file_paths}
                    if file_paths
                    else set(self.sources)
                )

                manifest = self._create_manifest(
                    list(source_paths),
                    self.contracts_folder,
                    contract_types,
                    initial_manifest=manifest,
                    name=self.name,
                    version=self.version,
                )

                # Cache the updated manifest so `self.cached_manifest` reads it next time
                self.manifest_cachefile.write_text(json.dumps(manifest.dict()))
                return manifest

        finally:
            if self.created_temporary_config_file and self.config_file.is_file():
                self.config_file.unlink()
                self.created_temporary_config_file = False


class ApeProject(BaseProject):
    """
    The default implementation of the :class:`~ape.api.projects.ProjectAPI`.
    By default, the `:class:`~ape.managers.project.ProjectManager` uses an
    ``ApeProject`` at the current-working directory.
    """


class BrownieProject(BaseProject):
    BROWNIE_CONFIG_FILE_NAME = "brownie-config.yaml"

    @property
    def brownie_config_path(self) -> Path:
        return self.path / self.BROWNIE_CONFIG_FILE_NAME

    @property
    def is_valid(self) -> bool:
        return self.brownie_config_path.is_file()

    def configure(self):
        # Migrate the brownie-config.yaml file to ape-config.yaml

        migrated_config_data = {}
        with open(self.brownie_config_path) as brownie_config_file:
            brownie_config_data = yaml.safe_load(brownie_config_file)

        # Migrate dependencies
        dependencies = []
        for dependency in brownie_config_data.get("dependencies", []):
            dependency_dict = {}
            dep_parts = dependency.split("/")
            dep_name = dep_parts[0]
            if len(dep_parts) > 1:
                dependency_dict["name"] = dep_name
                if "@" in dep_parts[1]:
                    suffix_parts = dep_parts[1].split("@")
                    dependency_dict["github"] = f"{dep_name}/{suffix_parts[0]}"
                    dependency_dict["version"] = suffix_parts[1]
                else:
                    dependency_dict["github"] = dep_parts[1]

            if dependency_dict:
                dependencies.append(dependency_dict)

        if dependencies:
            migrated_config_data["dependencies"] = dependencies

        # Migrate solidity remapping
        import_remapping = []
        if "compiler" in brownie_config_data:
            compiler_config = brownie_config_data["compiler"]
            if "solc" in compiler_config:
                available_dependencies = [d["name"] for d in dependencies]
                solidity_config = compiler_config["solc"]
                brownie_import_remapping = solidity_config.get("remappings", [])

                for remapping in brownie_import_remapping:
                    parts = remapping.split("=")
                    map_key = parts[0]
                    real_path = parts[1]

                    real_path_parts = real_path.split("/")
                    dependency_name = real_path_parts[0]

                    if dependency_name in available_dependencies:
                        suffix = real_path_parts[1]
                        if "@" in suffix:
                            version_id = suffix.split("@")[1]
                            key = f"{map_key}/{self.contracts_folder.stem}"
                            entry = f"{dependency_name}/{version_id}"
                            import_remapping.append(f"{key}={entry}")
                        else:
                            import_remapping.append(
                                f"{parts[0]}/{self.contracts_folder.stem}={dependency_name}"
                            )

        if import_remapping:
            migrated_config_data["solidity"] = {"import_remapping": import_remapping}

        super().configure(**migrated_config_data)
