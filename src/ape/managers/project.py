from pathlib import Path
from typing import Dict

from dataclassy import dataclass

from .config import ConfigManager


@dataclass
class ProjectManager:
    path: Path
    config: ConfigManager

    depedendencies: Dict[str, "ProjectManager"] = dict()

    def __init__(self):
        pass  # Look for depedencies from config

    def __str__(self) -> str:
        return f'Project("{self.path}")'

    def _cache_folder(self) -> Path:
        folder = self.path / ".build"
        # NOTE: If we use the cache folder, we expect it to exist
        folder.mkdir(exist_ok=True)
        return folder

    # NOTE: Using these paths should handle the case when the folder doesn't exist
    def _contracts_folder(self) -> Path:
        return self.path / "contracts"

    def _interfaces_folder(self) -> Path:
        return self.path / "interfaces"

    def _scripts_folder(self) -> Path:
        return self.path / "scripts"

    def _tests_folder(self) -> Path:
        return self.path / "tests"

    # TODO: Add `contracts` property, that gives attrdict of all compiled contract types in project
    # TODO: Add `manifest` property, that fully compiles and assembles the EthPM Manifest
    # NOTE: If project is a dependency, then the manifest doesn't need to be assembled
