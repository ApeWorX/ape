import os
import shutil
import tempfile
from pathlib import Path
from typing import Dict

import pytest

from ape.managers.project.dependency import NpmDependency


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
    name = "@gnosis.pm"
    package = "safe-singleton-factory"
    version = "1.0.0"
    with tempfile.TemporaryDirectory() as temp_dir:
        os.chdir(temp_dir)
        package_folder = Path(temp_dir) / "node_modules" / name / package
        contracts_folder = package_folder / "contracts"
        contracts_folder.mkdir(parents=True)
        package_json = package_folder / "package.json"
        package_json.write_text(f'{{"version": "{version}"}}')
        file = contracts_folder / "contract.json"
        source_content = '{"abi": []}'
        file.write_text(source_content)
        dependency = NpmDependency(name=package, npm=f"{name}/{package}", version=version)
        manifest = dependency.extract_manifest()
        assert manifest.sources
        assert str(manifest.sources["contract.json"].content) == f"{source_content}\n"


def test_compile(project_with_downloaded_dependencies):
    name = "OpenZeppelin"
    oz_442 = project_with_downloaded_dependencies.dependencies[name]["4.4.2"]
    # NOTE: the test data is pre-compiled because the ape-solidity plugin is required.
    actual = oz_442.compile()
    assert len(actual.contract_types) > 0


def test_compile_with_extra_settings(dependency_manager, project):
    settings = {".json": {"evm_version": "paris"}}
    path = "__test_path__"
    base_path = project.path / path
    contracts_path = base_path / "contracts"
    contracts_path.mkdir(parents=True)
    (contracts_path / "contract.json").write_text('{"abi": []}')

    data = {"name": "FooBar", "local": path, "config_override": settings}
    dependency = dependency_manager.decode_dependency(data)
    assert dependency.config_override == settings
