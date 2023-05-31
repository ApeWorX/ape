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
def local_dependency(project_with_dependency_config):
    return project_with_dependency_config.dependencies["testdependency"]["local"]


@pytest.fixture
def project_with_downloaded_dependencies(temp_config, config, oz_dependencies_config):
    manifests_directory = Path(__file__).parent / "data" / "manifests"
    oz_manifests = manifests_directory / "OpenZeppelin"
    oz_manifests_dest = config.packages_folder / "OpenZeppelin"

    if oz_manifests_dest.is_dir():
        shutil.rmtree(oz_manifests_dest)

    shutil.copytree(oz_manifests, oz_manifests_dest)
    with temp_config(oz_dependencies_config) as project:
        yield project

@pytest.fixture
def project_with_npm_dependency(temp_config, config):

    def _create_npm_dependency(version:str) -> Dict:
        return {
            "name": "safe-singleton-factory",
            "version": version,
            "npm": "gnosis.pm/safe-singleton-factory",
        }
    
    npm_depdency = _create_npm_dependency("1.0.3")
    pass

def test_two_dependencies_with_same_name(project_with_downloaded_dependencies):
    name = "OpenZeppelin"
    oz_310 = project_with_downloaded_dependencies.dependencies[name]["3.1.0"]
    oz_442 = project_with_downloaded_dependencies.dependencies[name]["4.4.2"]
    base_uri = "https://github.com/OpenZeppelin/openzeppelin-contracts/releases/tag"

    assert oz_310.version == "3.1.0"
    assert oz_310.name == name
    assert str(oz_310.uri) == f"{base_uri}/v3.1.0"
    assert oz_442.version == "4.4.2"
    assert oz_442.name == name
    assert str(oz_442.uri) == f"{base_uri}/v4.4.2"


def test_dependency_contracts_folder(config, local_dependency):
    """
    The local dependency fixture uses a longer contracts folder path.
    This test ensures that the contracts folder field is honored, specifically
    In the case when it contains sub-paths.
    """
    actual = local_dependency.contracts_folder
    assert actual == "source/v0.1"


def test_local_dependency(local_dependency, config):
    assert local_dependency.name == "testdependency"
    assert local_dependency.version_id == "local"
    expected = config.DATA_FOLDER / "packages" / "testdependency" / "local" / "testdependency.json"
    assert str(local_dependency.uri) == f"file://{expected}"


def test_access_dependency_contracts(project_with_downloaded_dependencies):
    name = "OpenZeppelin"
    oz_442 = project_with_downloaded_dependencies.dependencies[name]["4.4.2"]
    contract = oz_442.AccessControl
    assert contract.contract_type.name == "AccessControl"


@pytest.mark.parametrize("ref", ("main", "v1.0.0", "1.0.0"))
def test_dependency_using_reference(ref, recwarn, dependency_manager):
    dependency_config = {
        "github": "apeworx/testfoobartest",
        "name": "foobar",
        "ref": ref,
    }
    dependency = dependency_manager.decode_dependency(dependency_config)
    _ = dependency.cached_manifest
    assert dependency.version is None
    assert dependency.ref == ref
    assert str(dependency.uri) == f"https://github.com/apeworx/testfoobartest/tree/{ref}"

    # Tests against bug where we tried creating version objects out of branch names,
    # thus causing warnings to show in `ape test` runs.
    assert DeprecationWarning not in [w.category for w in recwarn.list]

def test_npm_dependency():
    pass
