import shutil
from pathlib import Path
from typing import Dict

import pytest
import yaml
from ethpm_types.manifest import PackageManifest

from ape.managers.project import BrownieProject


@pytest.fixture
def oz_dependencies_config():
    def _create_oz_dependency(version: str) -> Dict:
        return {
            "name": "OpenZeppelin",
            "version": version,
            "github": "OpenZeppelin/openzeppelin-contracts",
        }

    return {"dependencies": [_create_oz_dependency("3.1.0"), _create_oz_dependency("4.4.2")]}


@pytest.fixture
def already_downloaded_dependencies(temp_config, config, oz_dependencies_config):
    manifests_directory = Path(__file__).parent / "data" / "manifests"
    oz_manifests = manifests_directory / "OpenZeppelin"
    oz_manifests_dest = config.packages_folder / "OpenZeppelin"
    shutil.copytree(oz_manifests, oz_manifests_dest)
    with temp_config(oz_dependencies_config):
        yield


def test_two_dependencies_with_same_name(already_downloaded_dependencies, project_manager):
    name = "OpenZeppelin"
    oz_310 = project_manager.dependencies[name]["3.1.0"]
    oz_442 = project_manager.dependencies[name]["4.4.2"]

    assert oz_310.version == "3.1.0"
    assert oz_310.name == name
    assert oz_442.version == "4.4.2"
    assert oz_442.name == name


def test_extract_manifest(dependency_config, project_manager):
    # NOTE: Only setting dependency_config to ensure existence of project.
    manifest = project_manager.extract_manifest()
    assert type(manifest) == PackageManifest


def test_meta(temp_config, project_manager):
    meta_config = {
        "meta": {
            "authors": ["Test Testerson"],
            "license": "MIT",
            "description": "test",
            "keywords": ["testing"],
            "links": {"apeworx.io": "https://apeworx.io"},
        }
    }
    with temp_config(meta_config):
        assert project_manager.meta.authors == ["Test Testerson"]
        assert project_manager.meta.license == "MIT"
        assert project_manager.meta.description == "test"
        assert project_manager.meta.keywords == ["testing"]
        assert "https://apeworx.io" in project_manager.meta.links["apeworx.io"]


def test_dependency_with_longer_contracts_folder(
    dependency_config, config, mocker, project_manager
):
    spy = mocker.patch("ape.managers.project.types.yaml")
    _ = project_manager.dependencies
    assert spy.safe_dump.call_args, "Config file never created"
    call_config = spy.safe_dump.call_args[0][0]
    assert call_config["contracts_folder"] == "source/v0.1"


def test_brownie_project_configure(config, base_projects_directory):
    project_path = base_projects_directory / "BrownieProject"
    expected_config_file = project_path / "ape-config.yaml"
    if expected_config_file.is_file():
        # Left from previous run
        expected_config_file.unlink()

    project = BrownieProject(path=project_path, contracts_folder="contracts")
    project.configure()
    assert expected_config_file.is_file()

    with open(expected_config_file) as ape_config_file:
        mapped_config_data = yaml.safe_load(ape_config_file)

    # Ensure Solidity and dependencies configuration mapped correctly
    assert mapped_config_data["solidity"]["version"] == "0.6.12"
    assert mapped_config_data["solidity"]["import_remapping"] == [
        "@openzeppelin/contracts=OpenZeppelin/3.1.0"
    ]
    assert mapped_config_data["dependencies"][0]["name"] == "OpenZeppelin"
    assert mapped_config_data["dependencies"][0]["github"] == "OpenZeppelin/openzeppelin-contracts"
    assert mapped_config_data["dependencies"][0]["version"] == "3.1.0"

    expected_config_file.unlink()
