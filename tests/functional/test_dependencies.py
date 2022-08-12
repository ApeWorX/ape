import shutil
from pathlib import Path
from typing import Dict

import pytest


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


def test_dependency_with_longer_contracts_folder(
    dependency_config, config, mocker, project_manager
):
    spy = mocker.patch("ape.managers.project.types.yaml")
    _ = project_manager.dependencies
    assert spy.safe_dump.call_args, "Config file never created"
    call_config = spy.safe_dump.call_args[0][0]
    assert call_config["contracts_folder"] == "source/v0.1"


def test_dependency_with_non_version_version_id(recwarn, dependency_manager):
    dependency_config = {
        "github": "apeworx/testfoobartest",
        "name": "foobar",
        "branch": "main",
    }
    dependency = dependency_manager.decode_dependency(dependency_config)
    _ = dependency.cached_manifest

    # Tests against bug where we tried creating version objects out of branch names,
    # thus causing warnings to show in `ape test` runs.
    assert DeprecationWarning not in [w.category for w in recwarn.list]
