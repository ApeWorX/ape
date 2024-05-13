import json
import os
import shutil
from pathlib import Path

import pytest
from pydantic import ValidationError

import ape
from ape.utils import create_tempdir
from ape_pm.dependency import GithubDependency, NpmDependency


@pytest.fixture
def oz_dependencies_config():
    def _create_oz_dependency(version: str) -> dict:
        return {
            "name": "openzeppelin",
            "version": version,
            "github": "OpenZeppelin/openzeppelin-contracts",
        }

    return {"dependencies": [_create_oz_dependency("3.1.0"), _create_oz_dependency("4.4.2")]}


@pytest.fixture
def local_dependency(project_with_dependency_config):
    yield project_with_dependency_config.dependencies.get_dependency(
        "testdependency", "releases/v6"
    )


@pytest.fixture
def project_with_downloaded_dependencies(project, oz_dependencies_config):
    manifests_directory = Path(__file__).parent / "data" / "manifests"
    oz_manifests = manifests_directory / "openzeppelin"
    base = project.dependencies.packages_cache
    package_id = "OpenZeppelin_openzeppelin-contracts"
    oz_manifests_dest = base.manifests_folder / package_id
    oz_manifests_dest.mkdir(exist_ok=True, parents=True)

    # Also, copy in the API data
    for version in ("3.1.0", "4.4.2"):
        manifest_source = oz_manifests / version / "openzeppelin.json"
        manifest_dest = oz_manifests_dest / f"{version.replace('.', '_')}.json"
        manifest_dest.unlink(missing_ok=True)
        manifest_dest.write_text(manifest_source.read_text())
        api_dest = base.api_folder / package_id / f"{version.replace('.', '_')}.json"
        api_dest.unlink(missing_ok=True)
        cfg = [x for x in oz_dependencies_config["dependencies"] if x["version"] == version][0]
        api_dest.parent.mkdir(exist_ok=True, parents=True)
        api_dest.write_text(json.dumps(cfg))

    with project.temp_config(**oz_dependencies_config):
        yield project


def test_dependency_with_multiple_versions(project_with_downloaded_dependencies):
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
    assert local_dependency.version == "releases/v6"
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
    with create_tempdir() as temp_path:
        os.chdir(str(temp_path))

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

            dependency = NpmDependency(
                name=package,
                npm=f"{name}/{package}",
                version=version,
                project=ape.Project(temp_path),
            )
            dependency.fetch(temp_path / "foo")
            assert len([x for x in (temp_path / "foo").iterdir()]) > 0

            shutil.rmtree(package_folder)


def test_decode_dependency_with_config_override(project):
    with project.isolate_in_tempdir() as tmp_project:
        settings = {".json": {"evm_version": "paris"}}
        path = "__test_path__"
        base_path = tmp_project.path / path
        contracts_path = base_path / "contracts"
        contracts_path.mkdir(parents=True, exist_ok=True)
        (contracts_path / "contract.json").write_text('{"abi": []}')

        data = {"name": "FooBar", "local": path, "config_override": settings}
        dependency = tmp_project.dependencies.decode_dependency(data)
        assert dependency.config_override == settings


def test_project_load_contracts(project_with_downloaded_dependencies):
    name = "openzeppelin"
    options = project_with_downloaded_dependencies.dependencies[name]
    # NOTE: the test data is pre-compiled because the ape-solidity plugin is required.
    actual = options["4.4.2"].load_contracts()
    assert len(actual) > 0


def test_project_load_contracts_with_config_override(project):
    with project.isolate_in_tempdir() as tmp_project:
        # NOTE: It is important that `contracts_folder` is present in settings
        #  for this test to test against a previous bug where we got multiple values.
        override = {"contracts_folder": "src"}
        contracts_path = tmp_project.path / "src"
        contracts_path.mkdir(exist_ok=True, parents=True)
        (contracts_path / "contract.json").write_text('{"abi": []}')
        data = {"name": "FooBar", "local": f"{tmp_project.path}", "config_override": override}
        api = tmp_project.dependencies.decode_dependency(data)
        tmp_project.dependencies.install(api)
        dependency = tmp_project.dependencies.get(api.name, api.version_id)
        assert dependency.config.contracts_folder == "src"
        assert dependency.contracts_folder == dependency.path / "src"
        assert dependency.contracts_folder.is_dir()
        assert [x.name for x in dependency.sources.paths] == ["contract.json"]
        actual = dependency.load_contracts()
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


def test_get_dependency(project_with_downloaded_dependencies):
    dm = project_with_downloaded_dependencies.dependencies
    actual = dm.get_dependency("OpenZeppelin/openzeppelin-contracts", "4.4.2")
    assert actual.name == "openzeppelin"
    assert actual.version == "4.4.2"
    assert actual.package_id == "OpenZeppelin/openzeppelin-contracts"


def test_get_dependency_by_name(project_with_downloaded_dependencies):
    dm = project_with_downloaded_dependencies.dependencies
    actual = dm.get_dependency("openzeppelin", "4.4.2")
    assert actual.name == "openzeppelin"
    assert actual.version == "4.4.2"
    assert actual.package_id == "OpenZeppelin/openzeppelin-contracts"


def test_uninstall(project_with_downloaded_dependencies):
    name = "openzeppelin"
    version = "4.4.2"
    dm = project_with_downloaded_dependencies.dependencies
    dependency = dm.get_dependency(name, version)
    dependency.uninstall()
    assert not any(d.name == name and d.version == version for d in dm.installed)


def test_get_versions(project_with_downloaded_dependencies):
    dm = project_with_downloaded_dependencies.dependencies
    name = "openzeppelin"
    actual = list(dm.get_versions(name))
    assert len(actual) == 2
