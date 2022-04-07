import json
from pathlib import Path
from typing import List, Optional

import yaml
from ethpm_types import PackageManifest
from ethpm_types.utils import compute_checksum

from ape.api import ProjectAPI
from ape.logging import logger
from ape.managers.config import CONFIG_FILE_NAME
from ape.utils import get_all_files_in_directory, get_relative_path


class ApeProject(ProjectAPI):
    """
    The default implementation of the :class:`~ape.api.projects.ProjectAPI`.
    By default, the `:class:`~ape.managers.project.ProjectManager` uses an
    ``ApeProject`` at the current-working directory.
    """

    @property
    def is_valid(self) -> bool:
        if (self.path / CONFIG_FILE_NAME).exists():
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
            files.extend(self.contracts_folder.rglob(f"*{extension}"))

        return files

    def create_manifest(
        self, file_paths: Optional[List[Path]] = None, use_cache: bool = True
    ) -> PackageManifest:
        # Create a config file if one doesn't exist to forward values from
        # the root project's 'ape-config.yaml' 'dependencies:' config.
        config_file = self.path / CONFIG_FILE_NAME
        if not config_file.exists():
            config_data = {}
            if self.name:
                config_data["name"] = self.name
            if self.version:
                config_data["version"] = self.version
            if self.contracts_folder.name != "contracts":
                # Only sets when not default.
                config_data["contracts_folder"] = self.contracts_folder.name
            if config_data:
                with open(config_file, "w") as f:
                    yaml.safe_dump(config_data, f)

        # Load a cached or clean manifest (to use for caching)
        if self.cached_manifest and use_cache:
            manifest = self.cached_manifest
        else:
            manifest = PackageManifest()

            if self.manifest_cachefile.exists():
                self.manifest_cachefile.unlink()

        cached_sources = manifest.sources or {}
        cached_contract_types = manifest.contract_types or {}
        sources = {s for s in self.sources if s in file_paths} if file_paths else set(self.sources)

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
        with self.config_manager.using_project(self.path, contracts_folder=self.contracts_folder):
            compiled_contract_types = self.compiler_manager.compile(needs_compiling)
            contract_types.update(compiled_contract_types)

            # NOTE: Update contract types & re-calculate source code entries in manifest
            sources = (
                {s for s in self.sources if s in file_paths} if file_paths else set(self.sources)
            )

            dependencies = {c for c in get_all_files_in_directory(self.contracts_folder / ".cache")}
            for contract in dependencies:
                sources.add(contract)

            manifest = self._create_manifest(
                sources,
                self.contracts_folder,
                contract_types,
                initial_manifest=manifest,
            )

            # NOTE: Cache the updated manifest to disk (so ``self.cached_manifest`` reads next time)
            self.manifest_cachefile.write_text(json.dumps(manifest.dict()))
            return manifest
