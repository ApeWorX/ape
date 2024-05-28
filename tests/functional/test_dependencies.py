import json
import shutil
from pathlib import Path

import pytest
from ethpm_types import PackageManifest
from pydantic import ValidationError

import ape
from ape.managers.project import Dependency, LocalProject, PackagesCache, Project, ProjectManager
from ape.utils import create_tempdir
from ape_pm.dependency import GithubDependency, LocalDependency, NpmDependency


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
def project_with_downloaded_dependencies(project, oz_dependencies_config):
    # The path to source-test data.
    manifests_directory = Path(__file__).parent / "data" / "manifests"
    oz_manifests = manifests_directory / "openzeppelin"

    # Copy test-data in the DATA_FOLDER, as if these were already fetched.
    base = project.dependencies.packages_cache
    package_id = "OpenZeppelin_openzeppelin-contracts"
    oz_manifests_dest = base.manifests_folder / package_id
    oz_manifests_dest.mkdir(exist_ok=True, parents=True)

    for version in ("3.1.0", "4.4.2"):
        manifest_source = oz_manifests / version / "openzeppelin.json"
        manifest_dest = oz_manifests_dest / f"{version.replace('.', '_')}.json"
        manifest_dest.unlink(missing_ok=True)
        manifest_dest.write_text(manifest_source.read_text())

        # Also, copy in the API data
        api_dest = base.api_folder / package_id / f"{version.replace('.', '_')}.json"
        api_dest.unlink(missing_ok=True)
        cfg = [x for x in oz_dependencies_config["dependencies"] if x["version"] == version][0]
        api_dest.parent.mkdir(exist_ok=True, parents=True)
        api_dest.write_text(json.dumps(cfg))

    with project.temp_config(**oz_dependencies_config):
        yield project


def test_repr(project):
    assert isinstance(project, LocalProject), "Setup failed - expecting local project"
    actual = repr(project.dependencies)
    path = str(project.path).replace(str(Path.home()), "$HOME")
    expected = f"<DependencyManager project={path}>"
    assert actual == expected


def test_repr_manifest_project():
    """
    Tests against assuming the dependency manager is related
    to a local project (could be from a manifest-project).
    """
    manifest = PackageManifest()
    project = Project.from_manifest(manifest, config_override={"name": "testname123"})
    dm = project.dependencies
    actual = repr(dm)
    expected = "<DependencyManager project=testname123>"
    assert actual == expected


def test_len(project):
    actual = len(project.dependencies)
    expected = len(project.config.dependencies)
    assert actual == expected


@pytest.mark.parametrize("ref", ("main", "v1.0.0", "1.0.0"))
def test_decode_dependency_using_reference(ref, recwarn, project):
    dependency_config = {
        "github": "apeworx/testfoobartest",
        "name": "foobar",
        "ref": ref,
    }
    dependency = project.dependencies.decode_dependency(**dependency_config)
    assert dependency.version is None
    assert dependency.ref == ref
    assert str(dependency.uri) == f"https://github.com/apeworx/testfoobartest/tree/{ref}"

    # Tests against bug where we tried creating version objects out of branch names,
    # thus causing warnings to show in `ape test` runs.
    assert DeprecationWarning not in [w.category for w in recwarn.list]


def test_dependency_with_multiple_versions(project_with_downloaded_dependencies):
    """
    Testing the case where we have OpenZeppelin installed multiple times
    with different versions.
    """
    name = "openzeppelin"
    dm = project_with_downloaded_dependencies.dependencies

    # We can get both projects at once! One for each version.
    oz_310 = dm.get_dependency(name, "3.1.0", allow_install=False)
    oz_442 = dm.get_dependency(name, "4.4.2", allow_install=False)
    base_uri = "https://github.com/OpenZeppelin/openzeppelin-contracts/releases/tag"

    assert oz_310.version == "3.1.0"
    assert oz_310.name == name
    assert str(oz_310.uri) == f"{base_uri}/v3.1.0"
    assert oz_442.version == "4.4.2"
    assert oz_442.name == name
    assert str(oz_442.uri) == f"{base_uri}/v4.4.2"


def test_decode_dependency_with_config_override(project):
    with project.isolate_in_tempdir() as tmp_project:
        settings = {".json": {"evm_version": "paris"}}
        path = "__test_path__"
        base_path = tmp_project.path / path
        contracts_path = base_path / "contracts"
        contracts_path.mkdir(parents=True, exist_ok=True)
        (contracts_path / "contract.json").write_text('{"abi": []}')

        data = {"name": "FooBar", "local": path, "config_override": settings}
        dependency = tmp_project.dependencies.decode_dependency(**data)
        assert dependency.config_override == settings


def test_uri_map(project_with_dependency_config):
    actual = project_with_dependency_config.dependencies.uri_map
    here = Path(__file__).parent
    expected = f"file://{here}/data/projects/LongContractsFolder"
    assert "testdependency" in actual
    assert str(actual["testdependency"]) == expected


def test_get_dependency_by_package_id(project_with_downloaded_dependencies):
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


def test_get_versions(project_with_downloaded_dependencies):
    dm = project_with_downloaded_dependencies.dependencies
    name = "openzeppelin"
    actual = list(dm.get_versions(name))
    assert len(actual) == 2


def test_add(project):
    with project.isolate_in_tempdir() as tmp_project:
        contracts_path = tmp_project.path / "src"
        contracts_path.mkdir(exist_ok=True, parents=True)
        (contracts_path / "contract.json").write_text('{"abi": []}')
        data = {"name": "FooBar", "local": f"{tmp_project.path}"}

        dependency = project.dependencies.add(data)
        assert isinstance(dependency, Dependency)
        assert dependency.name == "foobar"
        assert dependency.version == "local"

        # After adding, we should be able to "get" it.
        dep2 = project.dependencies.get_dependency(
            dependency.package_id, dependency.version, allow_install=False
        )
        assert dep2 == dependency

        # Attempt to add again.
        dep3 = project.dependencies.add(data)
        assert dep3 == dependency


def test_add_dependency_with_dependencies(project, with_dependencies_project_path):
    dm = project.dependencies
    data = {"name": "wdep", "local": with_dependencies_project_path}
    actual = dm.add(data)
    assert actual.name == "wdep"
    assert actual.version == "local"


def test_install(project):
    with project.isolate_in_tempdir() as tmp_project:
        contracts_path = tmp_project.path / "src"
        contracts_path.mkdir(exist_ok=True, parents=True)
        (contracts_path / "contract.json").write_text('{"abi": []}')
        data = {"name": "FooBar", "local": f"{tmp_project.path}"}

        # Show can install from DependencyManager.
        dependency = tmp_project.dependencies.install(**data)
        assert isinstance(dependency, Dependency)

        # Show can install from Dependency.
        project = dependency.install()
        assert isinstance(project, ProjectManager)

        # Delete project path (but not manifest) and install again.
        shutil.rmtree(dependency.project_path)
        dependency._installation = None
        project = dependency.install()
        assert isinstance(project, ProjectManager)
        assert dependency.project_path.is_dir()  # Was re-created from manifest sources.


def test_install_dependencies_of_dependencies(project, with_dependencies_project_path):
    dm = project.dependencies
    actual = dm.install(local=with_dependencies_project_path, name="wdep")
    assert actual.name == "wdep"
    # TODO: Check deps of deps also installed
    # deps_of_deps = [x for x in actual.project.dependencies.specified]


def test_uninstall(project_with_downloaded_dependencies):
    name = "openzeppelin"
    version = "4.4.2"
    dm = project_with_downloaded_dependencies.dependencies
    dependency = dm.get_dependency(name, version)
    dependency.uninstall()
    assert not any(d.name == name and d.version == version for d in dm.installed)


def test_unpack(project_with_downloaded_dependencies):
    dm = project_with_downloaded_dependencies.dependencies
    dep = dm.get_dependency("openzeppelin", "4.4.2")
    with create_tempdir() as tempdir:
        created = list(dep.unpack(tempdir))
        assert len(created) == 1
        assert created[0].package_id == "OpenZeppelin/openzeppelin-contracts"

        files = [x.name for x in (tempdir / "openzeppelin" / "4.4.2" / "contracts").iterdir()]
        assert "token" in files
        assert "access" in files


def test_unpack_dependencies_of_dependencies(project, with_dependencies_project_path):
    dep = project.dependencies.install(local=with_dependencies_project_path, name="wdep")
    with create_tempdir() as tempdir:
        dep.unpack(tempdir)

        # TODO: Check for dependency of dependency!


class TestPackagesCache:
    @pytest.fixture
    def cache(self):
        return PackagesCache()

    def test_root(self, cache, data_folder):
        actual = cache.root
        expected = data_folder / "packages"
        assert actual == expected

    def test_api_folder(self, cache, data_folder):
        actual = cache.api_folder
        expected = data_folder / "packages" / "api"
        assert actual == expected

    def test_get_api_path(self, cache, data_folder):
        package_id = "this/is/my_package-ID"
        version = "version12/5.54"
        actual = cache.get_api_path(package_id, version)
        expected = (
            data_folder / "packages" / "api" / "this_is_my_package-ID" / "version12_5_54.json"
        )
        assert actual == expected

    def test_cache_api(self, cache):
        dep = LocalDependency(name="depabc", local=Path("depabc"))
        path = cache.cache_api(dep)
        assert path.is_file()
        assert path == cache.get_api_path("depabc", "local")
        actual = json.loads(path.read_text())
        assert actual == {"name": "depabc", "local": "depabc"}


class TestLocalDependency:
    NAME = "testlocaldep"
    VERSION = "1.0.0"
    PATH = Path.cwd()

    @pytest.fixture
    def dependency(self):
        return LocalDependency(local=self.PATH, name=self.NAME, version=self.VERSION)

    @property
    def clean_path(self) -> str:
        return str(self.PATH).replace(str(Path.home()), "$HOME")

    def test_repr(self, dependency):
        actual = repr(dependency)
        expected = f"<LocalDependency local={self.clean_path}, version={self.VERSION}>"
        assert actual == expected

    def test_name(self, dependency):
        assert dependency.name == self.NAME

    def test_version(self, dependency):
        assert dependency.version == self.VERSION

    def test_uri(self, dependency):
        assert dependency.uri == self.PATH.as_uri()


class TestNpmDependency:
    NAME = "@gnosis.pm"
    PACKAGE = "safe-singleton-factory"
    VERSION = "1.0.0"

    @pytest.fixture
    def project_with_npm_dependency(self):
        with create_tempdir() as temp_path:
            yield ape.Project(temp_path)

    @pytest.fixture(params=("local", "global"))
    def node_modules_path(self, project_with_npm_dependency, request, mock_home_directory):
        pm = project_with_npm_dependency
        base = pm.path if request.param == "local" else mock_home_directory
        package_folder = base / "node_modules" / self.NAME / self.PACKAGE
        contracts_folder = package_folder / "contracts"
        contracts_folder.mkdir(parents=True)
        package_json = package_folder / "package.json"
        package_json.write_text(f'{{"version": "{self.VERSION}"}}')
        file = contracts_folder / "contract.json"
        source_content = '{"abi": []}'
        file.write_text(source_content)
        yield base

    def test_fetch(self, node_modules_path, project_with_npm_dependency):
        pm = project_with_npm_dependency
        dependency = NpmDependency(
            name=self.PACKAGE,
            npm=f"{self.NAME}/{self.PACKAGE}",
            version=self.VERSION,
            project=pm,
        )
        dependency.fetch(pm.path / "foo")
        assert len([x for x in (pm.path / "foo").iterdir()]) > 0


class TestGitHubDependency:
    def test_ref_or_version_is_required(self):
        expected = r"GitHub dependency must have either ref or version specified"
        with pytest.raises(ValidationError, match=expected):
            _ = GithubDependency(name="foo", github="asdf")


class TestDependency:
    @pytest.fixture
    def api(self):
        return LocalDependency(local=Path.cwd(), name="ooga", version="1.0.0")

    @pytest.fixture
    def dependency(self, api, project):
        return Dependency(api, project)

    def test_repr(self, dependency):
        actual = repr(dependency)
        path = str(Path.cwd()).replace(str(Path.home()), "$HOME")
        expected = f"<Dependency package={path} version=1.0.0>"
        assert actual == expected

    def test_project_path(self, dependency, data_folder):
        actual = dependency.project_path
        name = dependency.api.package_id.replace("/", "_")
        expected = data_folder / "packages" / "projects" / name / "1_0_0"
        assert actual == expected

    def test_api_path(self, dependency, data_folder):
        actual = dependency.api_path
        name = dependency.api.package_id.replace("/", "_")
        expected = data_folder / "packages" / "api" / name / "1_0_0.json"
        assert actual == expected

    def test_manifest_path(self, dependency, data_folder):
        actual = dependency.manifest_path
        name = dependency.api.package_id.replace("/", "_")
        expected = data_folder / "packages" / "manifests" / name / "1_0_0.json"
        assert actual == expected


class TestProject:
    """
    All tests related to a dependency's project.
    """

    @pytest.fixture
    def project_from_dependency(self, project_with_dependency_config):
        dependencies = project_with_dependency_config.dependencies
        return dependencies["testdependency"]["releases/v6"]

    def test_path(self, project_from_dependency):
        assert project_from_dependency.path.is_dir()

    def test_contracts_folder(self, project_from_dependency):
        """
        The local dependency fixture uses a longer contracts folder path.
        This test ensures that the contracts folder field is honored, specifically
        In the case when it contains sub-paths.
        """
        actual = project_from_dependency.contracts_folder
        expected = project_from_dependency.path / "source" / "v0.1"
        assert actual == expected

    def test_load_contracts(self, project_with_downloaded_dependencies):
        name = "openzeppelin"
        options = project_with_downloaded_dependencies.dependencies[name]
        project = options["4.4.2"]
        # NOTE: the test data is pre-compiled because the ape-solidity plugin is required.
        actual = project.load_contracts()
        assert len(actual) > 0

    def test_load_contracts_with_config_override(self, project):
        with project.isolate_in_tempdir() as tmp_project:
            # NOTE: It is important that `contracts_folder` is present in settings
            #  for this test to test against a previous bug where we got multiple values.
            override = {"contracts_folder": "src"}
            contracts_path = tmp_project.path / "src"
            contracts_path.mkdir(exist_ok=True, parents=True)
            (contracts_path / "contract.json").write_text('{"abi": []}')
            data = {"name": "FooBar", "local": f"{tmp_project.path}", "config_override": override}
            tmp_project.dependencies.install(**data)
            proj = tmp_project.dependencies.get("foobar", "local")
            assert proj.config.contracts_folder == "src"

            assert proj.contracts_folder == proj.path / "src"
            assert proj.contracts_folder.is_dir()
            assert [x.name for x in proj.sources.paths] == ["contract.json"]
            actual = proj.load_contracts()
            assert len(actual) > 0

    def test_getattr(self, project_with_downloaded_dependencies):
        """
        Access contracts using __getattr__ from the dependency's project.
        """
        name = "openzeppelin"
        oz_442 = project_with_downloaded_dependencies.dependencies.get_dependency(name, "4.4.2")
        contract = oz_442.project.AccessControl
        assert contract.contract_type.name == "AccessControl"
