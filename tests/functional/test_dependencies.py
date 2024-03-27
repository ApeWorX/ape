import json
import os
import shutil
import tempfile
from pathlib import Path
from typing import Dict

import pytest
from pydantic import ValidationError

from ape_pm.dependency import GithubDependency, NpmDependency


@pytest.fixture
def oz_dependencies_config():
    def _create_oz_dependency(version: str) -> Dict:
        return {
            "name": "openzeppelin",
            "version": version,
            "github": "OpenZeppelin/openzeppelin-contracts",
        }

    return {"dependencies": [_create_oz_dependency("3.1.0"), _create_oz_dependency("4.4.2")]}


@pytest.fixture
def local_dependency(project_with_dependency_config):
    yield project_with_dependency_config.dependencies.get_dependency("testdependency", "local")


@pytest.fixture
def project_with_downloaded_dependencies(project, oz_dependencies_config):
    manifests_directory = Path(__file__).parent / "data" / "manifests"
    oz_manifests = manifests_directory / "openzeppelin"
    base = project.dependencies.packages_cache
    oz_manifests_dest = base.projects_folder / "openzeppelin"

    if oz_manifests_dest.is_dir():
        shutil.rmtree(oz_manifests_dest)

    shutil.copytree(oz_manifests, oz_manifests_dest)

    # Also, copy in the API data
    for version in ("3.1.0", "4.4.2"):
        api_dest = base.api_folder / f"openzeppelin_{version}.json"
        api_dest.unlink(missing_ok=True)
        cfg = [x for x in oz_dependencies_config["dependencies"] if x["version"] == version][0]
        api_dest.parent.mkdir(exist_ok=True, parents=True)
        api_dest.write_text(json.dumps(cfg))

    with project.temp_config(**oz_dependencies_config):
        yield project


def test_two_dependencies_with_same_name(project_with_downloaded_dependencies):
    name = "openzeppelin"
    oz_310 = project_with_downloaded_dependencies.dependencies.get_dependency(name, "3.1.0")
    oz_442 = project_with_downloaded_dependencies.dependencies.get_dependency(name, "4.4.2")
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
    actual = local_dependency.project.config.contracts_folder
    assert actual == "source/v0.1"


def test_local_dependency(local_dependency, config):
    assert local_dependency.name == "testdependency"
    assert local_dependency.version == "local"
    assert str(local_dependency.uri).startswith("file://")


def test_access_dependency_contracts(project_with_downloaded_dependencies):
    name = "openzeppelin"
    oz_442 = project_with_downloaded_dependencies.dependencies.get_dependency(name, "4.4.2")
    contract = oz_442.project.AccessControl
    assert contract.contract_type.name == "AccessControl"


@pytest.mark.parametrize("ref", ("main", "v1.0.0", "1.0.0"))
def test_decode_dependency_using_reference(ref, recwarn, project):
    dependency_config = {
        "github": "apeworx/testfoobartest",
        "name": "foobar",
        "ref": ref,
    }
    dependency = project.dependencies.decode_dependency(dependency_config)
    assert dependency.version is None
    assert dependency.ref == ref
    assert str(dependency.uri) == f"https://github.com/apeworx/testfoobartest/tree/{ref}"

    # Tests against bug where we tried creating version objects out of branch names,
    # thus causing warnings to show in `ape test` runs.
    assert DeprecationWarning not in [w.category for w in recwarn.list]


def test_npm_dependency(mock_home_directory):
    name = "@gnosis.pm"
    package = "safe-singleton-factory"
    version = "1.0.0"
    dependency = NpmDependency(name=package, npm=f"{name}/{package}", version=version)
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir).resolve()
        os.chdir(temp_dir)

        # Test with both local and global node modules install.
        for base in (temp_path, mock_home_directory):
            package_folder = base / "node_modules" / name / package
            contracts_folder = package_folder / "contracts"
            contracts_folder.mkdir(parents=True)
            package_json = package_folder / "package.json"
            package_json.write_text(f'{{"version": "{version}"}}')
            file = contracts_folder / "contract.json"
            source_content = '{"abi": []}'
            file.write_text(source_content)

            dependency.fetch(temp_path / "foo")
            assert len([x for x in (temp_path / "foo").iterdir()]) > 0

            shutil.rmtree(package_folder)


def test_decode_dependency_with_config_override(project):
    with project.sandbox() as sandbox:
        settings = {".json": {"evm_version": "paris"}}
        path = "__test_path__"
        base_path = sandbox.path / path
        contracts_path = base_path / "contracts"
        contracts_path.mkdir(parents=True, exist_ok=True)
        (contracts_path / "contract.json").write_text('{"abi": []}')

        data = {"name": "FooBar", "local": path, "config_override": settings}
        dependency = sandbox.dependencies.decode_dependency(data)
        assert dependency.config_override == settings


def test_project_load_contracts(project_with_downloaded_dependencies):
    name = "openzeppelin"
    options = project_with_downloaded_dependencies.dependencies[name]
    # NOTE: the test data is pre-compiled because the ape-solidity plugin is required.
    actual = options["4.4.2"].project.load_contracts()
    assert len(actual) > 0


def test_project_load_contracts_with_config_override(project):
    with project.sandbox() as sandbox:
        # NOTE: It is important that `contracts_folder` is present in settings
        #  for this test to test against a previous bug where we got multiple values.
        override = {"contracts_folder": "src"}
        contracts_path = sandbox.path / "src"
        contracts_path.mkdir(exist_ok=True, parents=True)
        (contracts_path / "contract.json").write_text('{"abi": []}')
        data = {"name": "FooBar", "local": f"{sandbox.path}", "config_override": override}
        api = sandbox.dependencies.decode_dependency(data)
        sandbox.dependencies.install(api)
        dependency = sandbox.dependencies.get(api.name, api.version_id)
        assert dependency.project
        actual = dependency.project.load_contracts()
        assert len(actual) > 0


def test_github_dependency_ref_or_version_is_required():
    expected = r"GitHub dependency must have either ref or version specified"
    with pytest.raises(ValidationError, match=expected):
        _ = GithubDependency(name="foo", github="asdf")


def test_uri_map(project_with_dependency_config):
    actual = project_with_dependency_config.dependencies.uri_map
    here = Path(__file__).parent
    expected = f"file://{here}/data/projects/LongContractsFolder"
    assert "testdependency" in actual
    assert str(actual["testdependency"]) == expected
