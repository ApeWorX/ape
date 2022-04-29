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
    def is_valid(self) -> bool:
        if (self.path / APE_CONFIG_FILE_NAME).exists():
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
        config_file = self.path / APE_CONFIG_FILE_NAME

        # Don't override existing config file.
        if config_file.exists():
            return

        config_data = {**kwargs}
        if self.name:
            config_data["name"] = self.name
        if self.version:
            config_data["version"] = self.version

        config_data["contracts_folder"] = self.contracts_folder.name
        with open(config_file, "w") as f:
            yaml.safe_dump(config_data, f)

            # Indicate that we need to clean up the file later.
            self.created_temporary_config_file = True

    def create_manifest(
        self, file_paths: Optional[List[Path]] = None, use_cache: bool = True
    ) -> PackageManifest:
        # Create a config file if one doesn't exist to forward values from
        # the root project's 'ape-config.yaml' 'dependencies:' config.
        config_file = self.path / APE_CONFIG_FILE_NAME

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
            sources = (
                {s for s in self.sources if s in file_paths} if file_paths else set(self.sources)
            )

            # Filter out deleted sources
            deleted_source_ids = cached_sources.keys() - set(
                map(str, [get_relative_path(s, self.contracts_folder) for s in sources])
            )
            contract_types = {
                name: contract_type
                for name, contract_type in cached_contract_types.items()
                if contract_type.source_id not in deleted_source_ids
            }

            def file_needs_compiling(source: Path) -> bool:
                path = str(get_relative_path(source, self.contracts_folder))

                if path not in cached_sources:
                    return True  # New file added

                cached = cached_sources[path]
                cached.compute_checksum(algorithm="md5")
                assert cached.checksum  # For mypy

                source_file = self.contracts_folder / source
                checksum = compute_checksum(
                    source_file.read_bytes(),
                    algorithm=cached.checksum.algorithm,
                )

                return checksum != cached.checksum.hash  # Contents changed

            # NOTE: Filter by checksum to only update what's needed
            needs_compiling = list(filter(file_needs_compiling, sources))

            # Set the context in case compiling a dependency (or anything outside the root project).
            with self.config_manager.using_project(
                self.path, contracts_folder=self.contracts_folder
            ):
                self.project_manager._load_dependencies()
                compiled_contract_types = self.compiler_manager.compile(needs_compiling)
                contract_types.update(compiled_contract_types)

                # NOTE: Update contract types & re-calculate source code entries in manifest
                sources = (
                    {s for s in self.sources if s in file_paths}
                    if file_paths
                    else set(self.sources)
                )

                dependencies = {
                    c for c in get_all_files_in_directory(self.contracts_folder / ".cache")
                }
                for contract in dependencies:
                    sources.add(contract)

                manifest = self._create_manifest(
                    sources,
                    self.contracts_folder,
                    contract_types,
                    initial_manifest=manifest,
                )

                # Cache the updated manifest so `self.cached_manifest` reads it next time
                self.manifest_cachefile.write_text(json.dumps(manifest.dict()))
                return manifest

        finally:
            if self.created_temporary_config_file and config_file.is_file():
                config_file.unlink()
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
