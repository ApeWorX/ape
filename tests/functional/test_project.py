import shutil
from pathlib import Path
from typing import Dict

import pytest
from ethpm_types.manifest import PackageManifest


@pytest.fixture
def dependencies_config():
    def _create_oz_dependency(version: str) -> Dict:
        return {
            "name": "OpenZeppelin",
            "version": version,
            "github": "OpenZeppelin/openzeppelin-contracts",
        }

    return {"dependencies": [_create_oz_dependency("3.1.0"), _create_oz_dependency("4.4.2")]}


@pytest.fixture
def already_downloaded_dependencies(temp_config, config, dependencies_config):
    manifests_directory = Path(__file__).parent / "data" / "manifests"
    oz_manifests = manifests_directory / "OpenZeppelin"
    oz_manifests_dest = config.packages_folder / "OpenZeppelin"
    shutil.copytree(oz_manifests, oz_manifests_dest)
    with temp_config(dependencies_config, config):
        yield


def test_two_dependencies_with_same_name(already_downloaded_dependencies, project):
    name = "OpenZeppelin"
    oz_310 = project.dependencies[name]["3.1.0"]
    oz_442 = project.dependencies[name]["4.4.2"]

    assert oz_310.version == "3.1.0"
    assert oz_310.name == name
    assert oz_442.version == "4.4.2"
    assert oz_442.name == name


def test_extract_manifest_type(project):
    manifest = project.project_manager.extract_manifest()
    assert type(manifest) == PackageManifest
