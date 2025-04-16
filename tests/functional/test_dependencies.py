import json
import os
import shutil
from pathlib import Path

import pytest
from ethpm_types import PackageManifest
from pydantic import ValidationError

import ape
from ape.exceptions import ProjectError
from ape.logging import LogLevel, logger
from ape.managers.project import Dependency, LocalProject, PackagesCache, Project, ProjectManager
from ape.utils import create_tempdir
from ape_pm.dependency import GithubDependency, LocalDependency, NpmDependency, PythonDependency
from tests.conftest import skip_if_plugin_installed


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


def test_dependency_with_multiple_versions(project):
    """
    Testing the case where we have OpenZeppelin installed multiple times
    with different versions.
    """
    name = "openzeppelin"
    dm = project.dependencies

    # We can get both projects at once! One for each version.
    oz_496 = dm.get_dependency(
        name,
        "4.9.6",
    )
    oz_520 = dm.get_dependency(name, "5.2.0")
    base_uri = "https://github.com/OpenZeppelin/openzeppelin-contracts/releases/tag"

    assert oz_496.version == "4.9.6"
    assert oz_496.name == name
    assert str(oz_496.uri) == f"{base_uri}/v4.9.6"
    assert oz_520.version == "5.2.0"
    assert oz_520.name == name
    assert str(oz_520.uri) == f"{base_uri}/v5.2.0"


def test_decode_dependency_with_config_override(temp_project):
    settings = {".json": {"evm_version": "paris"}}
    path = "__test_path__"
    base_path = temp_project.path / path
    contracts_path = base_path / "contracts"
    contracts_path.mkdir(parents=True, exist_ok=True)
    (contracts_path / "contract.json").write_text('{"abi": []}', encoding="utf8")

    data = {"name": "FooBar", "local": path, "config_override": settings}
    dependency = temp_project.dependencies.decode_dependency(**data)
    assert dependency.config_override == settings


def test_uri_map(project_with_dependency_config):
    actual = project_with_dependency_config.dependencies.uri_map
    here = Path(__file__).parent
    # Wrap in Path to handle Windows.
    expected = Path(f"file://{here}/data/projects/LongContractsFolder")
    assert "testdependency" in actual
    assert Path(str(actual["testdependency"])) == expected


def test_get_dependency_by_package_id(project):
    dm = project.dependencies
    actual = dm.get_dependency("OpenZeppelin/openzeppelin-contracts", "4.9.6")
    assert actual.name == "openzeppelin"
    assert actual.version == "4.9.6"
    assert actual.package_id == "OpenZeppelin/openzeppelin-contracts"


def test_get_dependency_by_name(project):
    dm = project.dependencies
    actual = dm.get_dependency("openzeppelin", "4.9.6")
    assert actual.name == "openzeppelin"
    assert actual.version == "4.9.6"
    assert actual.package_id == "OpenZeppelin/openzeppelin-contracts"


def test_get_versions_using_package_id(project):
    dm = project.dependencies
    package_id = "OpenZeppelin/openzeppelin-contracts"
    actual = list(dm.get_versions(package_id))
    assert len(actual) >= 2


def test_get_versions_using_name(project):
    dm = project.dependencies
    name = "openzeppelin"
    actual = list(dm.get_versions(name))
    assert len(actual) >= 2


def test_getitem_and_contains_and_get(project):
    dm = project.dependencies
    name = "openzeppelin"
    versions = dm[name]
    assert "5.2.0" in versions
    assert "v5.2.0" in versions  # Also allows v-prefix.
    assert (
        versions["5.2.0"] == versions["v5.2.0"] == versions.get("5.2.0") == versions.get("v5.2.0")
    )
    assert isinstance(versions["5.2.0"], LocalProject)


def test_add(temp_project):
    contracts_path = temp_project.path / "src"
    contracts_path.mkdir(exist_ok=True, parents=True)
    (contracts_path / "contract.json").write_text('{"abi": []}', encoding="utf8")
    data = {"name": "FooBar", "local": f"{temp_project.path}"}

    dependency = temp_project.dependencies.add(data)
    assert isinstance(dependency, Dependency)
    assert dependency.name == "foobar"
    assert dependency.version == "local"

    # After adding, we should be able to "get" it.
    dep2 = temp_project.dependencies.get_dependency(
        dependency.package_id, dependency.version, allow_install=False
    )
    assert dep2 == dependency

    # Attempt to add again.
    dep3 = temp_project.dependencies.add(data)
    assert dep3 == dependency


def test_add_dependency_with_dependencies(project, with_dependencies_project_path):
    dm = project.dependencies
    data = {"name": "wdep", "local": with_dependencies_project_path}
    actual = dm.add(data)
    assert actual.name == "wdep"
    assert actual.version == "local"


def test_get_project_dependencies(project, ape_caplog):
    installed_package = {"name": "web3", "site_package": "web3"}
    not_installed_package = {
        "name": "apethisisnotarealpackageape",
        "site_package": "apethisisnotarealpackageape",
    }
    with project.temp_config(dependencies=[installed_package, not_installed_package]):
        dm = project.dependencies
        actual = list(dm.get_project_dependencies())
        logs = ape_caplog.head
        assert len(actual) == 2
        assert actual[0].name == "web3"
        assert actual[0].installed
        assert actual[1].name == "apethisisnotarealpackageape"
        assert not actual[1].installed
        assert "Dependency 'apethisisnotarealpackageape' not installed." in logs


def test_install(temp_project, mocker):
    contracts_path = temp_project.path / "src"
    contracts_path.mkdir(exist_ok=True, parents=True)
    (contracts_path / "contract.json").write_text('{"abi": []}', encoding="utf8")
    data = {"name": "FooBar", "local": f"{temp_project.path}"}
    install_dep_spy = mocker.spy(temp_project.dependencies, "install_dependency")

    # Show can install from DependencyManager.
    dependency = temp_project.dependencies.install(**data)
    assert isinstance(dependency, Dependency)
    # NOTE: Here, we are mostly testing that `use_cache=False` was not passed.
    assert install_dep_spy.call_count == 1

    # Show can install from Dependency.
    project = dependency.install()
    assert isinstance(project, ProjectManager)

    # Delete project path (but not manifest) and install again.
    shutil.rmtree(dependency.project_path)
    dependency._installation = None
    project = dependency.install()
    assert isinstance(project, ProjectManager)
    assert dependency.project_path.is_dir()  # Was re-created from manifest contracts.

    # Force install and prove it actually reinstalls.
    dependency.uninstall()
    dependency.install(use_cache=False, recurse=False)
    assert dependency.installed


def test_install_dependencies_of_dependencies(project, with_dependencies_project_path):
    dm = project.dependencies
    actual = dm.install(local=with_dependencies_project_path, name="wdep")
    assert actual.name == "wdep"
    # TODO: Check deps of deps also installed
    # deps_of_deps = [x for x in actual.project.dependencies.specified]


@pytest.mark.parametrize("name", ("openzeppelin", "OpenZeppelin/openzeppelin-contracts"))
def test_uninstall(name, project):
    version = "4.9.6"
    dm = project.dependencies
    dependency = dm.get_dependency(name, version)
    with dependency._cache.isolate_changes():
        dependency.uninstall()
        assert not any(
            (d.name == name or d.package_id == name) and d.version == version for d in dm.installed
        )


def test_unpack(project):
    dm = project.dependencies
    dep = dm.get_dependency("openzeppelin", "4.9.6")
    with create_tempdir() as tempdir:
        created = list(dep.unpack(tempdir))
        assert len(created) == 3
        assert any([x.name == "openzeppelin" for x in created])
        assert created[0].package_id == "OpenZeppelin/openzeppelin-contracts"

        files = [x.name for x in (tempdir / "openzeppelin" / "4.9.6" / "contracts").iterdir()]
        assert "token" in files
        assert "access" in files


def test_unpack_dependencies_of_dependencies(project, with_dependencies_project_path):
    dep = project.dependencies.install(local=with_dependencies_project_path, name="wdep")
    with create_tempdir() as tempdir:
        list(dep.unpack(tempdir))
        subdirs = [x.name for x in tempdir.iterdir() if x.is_dir()]
        assert "sub-dependency" in subdirs


def test_unpack_no_contracts_folder(project, with_dependencies_project_path):
    dep = project.dependencies.install(local=with_dependencies_project_path, name="wdep")
    with create_tempdir() as tempdir:
        list(dep.unpack(tempdir))
        subdirs = [x.name for x in tempdir.iterdir() if x.is_dir()]
        assert "empty-dependency" in subdirs


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

    def test_cache_api_when_v_prefix_exists(self, cache):
        # First, cache the v-prefix
        dep = LocalDependency(name="depabc", local=Path("depabc"), version="v1.0.0")
        path0 = cache.cache_api(dep)
        assert path0.is_file()

        # Now, try to cache again w/o v prefix
        dep.version = "1.0.0"
        path1 = cache.cache_api(dep)
        assert path1 == path0

    def test_cache_api_when_non_v_prefix_exists(self, cache):
        # First, cache the non-v-prefix
        dep = LocalDependency(name="depabc", local=Path("depabc"), version="1.0.0")
        path0 = cache.cache_api(dep)
        assert path0.is_file()

        # Now, try to cache again with the v prefix
        dep.version = "v1.0.0"
        path1 = cache.cache_api(dep)
        assert path1 == path0

    def test_get_manifest_path(self, cache, data_folder):
        package_id = "this/is/my_package-ID"
        version = "version12/5.54"
        actual = cache.get_manifest_path(package_id, version)
        expected = (
            data_folder / "packages" / "manifests" / "this_is_my_package-ID" / "version12_5_54.json"
        )
        assert actual == expected

    def test_get_manifest_path_v_prefix_exists(self, cache, data_folder):
        file = data_folder / "packages" / "manifests" / "manifest-pkg-test-1" / "v1_0_0.json"
        file.parent.mkdir(parents=True, exist_ok=True)
        file.touch()

        # Requesting w/o v-prefix. Should still work.
        path = cache.get_manifest_path("manifest-pkg-test-1", "1.0.0")
        assert path == file

    def test_get_manifest_path_non_v_prefix_exists(self, cache, data_folder):
        file = data_folder / "packages" / "manifests" / "manifest-pkg-test-2" / "1_0_0.json"
        file.parent.mkdir(parents=True, exist_ok=True)
        file.touch()

        # Requesting w/o v-prefix. Should still work.
        path = cache.get_manifest_path("manifest-pkg-test-2", "v1.0.0")
        assert path == file

    def test_get_project_path(self, cache, data_folder):
        path = data_folder / "packages" / "projects" / "project-test-1" / "local"
        actual = cache.get_project_path("project-test-1", "local")
        assert actual == path

    def test_get_project_path_missing_v_prefix(self, cache, data_folder):
        path = data_folder / "packages" / "projects" / "project-test-1" / "v1_0_0"
        path.mkdir(parents=True, exist_ok=True)
        # Missing v-prefix on request.
        actual = cache.get_project_path("project-test-1", "1.0.0")
        assert actual == path

    def test_get_project_path_unneeded_v_prefix(self, cache, data_folder):
        path = data_folder / "packages" / "projects" / "project-test-2" / "1_0_0"
        path.mkdir(parents=True, exist_ok=True)
        # Unneeded v-prefix on request.
        actual = cache.get_project_path("project-test-2", "v1.0.0")
        assert actual == path

    def test_isolate_cache_changes(self, cache):
        dep = LocalDependency(name="isotestdep", local=Path("isotestdep"), version="v1.0.0")
        with cache.isolate_changes():
            path = cache.cache_api(dep)
            assert path.is_file()

        assert not path.is_file()


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
        package_json.write_text(f'{{"version": "{self.VERSION}"}}', encoding="utf8")
        file = contracts_folder / "contract.json"
        source_content = '{"abi": []}'
        file.write_text(source_content, encoding="utf8")
        return base

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
    @pytest.fixture
    def mock_client(self, mocker):
        return mocker.MagicMock()

    def test_ref_or_version_is_required(self):
        expected = r"GitHub dependency must have either ref or version specified"
        with pytest.raises(ValidationError, match=expected):
            _ = GithubDependency(name="foo", github="asdf")

    def test_name_from_github(self):
        """
        When not given a name, it is derived from the github suffix.
        """
        dependency = GithubDependency(  # type: ignore
            github="ApeWorX/ApeNotAThing", version="3.0.0"
        )
        assert dependency.name == "apenotathing"

    def test_fetch_given_version(self, mock_client):
        dependency = GithubDependency(
            github="ApeWorX/ApeNotAThing", version="3.0.0", name="apetestdep"
        )
        dependency._github_client = mock_client
        with create_tempdir() as path:
            dependency.fetch(path)

        mock_client.download_package.assert_called_once_with(
            "ApeWorX", "ApeNotAThing", "3.0.0", path
        )

    def test_fetch_missing_v_prefix(self, mock_client):
        """
        Show if the version expects a v-prefix but you don't
        provide one that it still works.
        """
        dependency = GithubDependency(
            github="ApeWorX/ApeNotAThing", version="3.0.0", name="apetestdep"
        )
        dependency._github_client = mock_client

        # Simulate only v-prefix succeeding from GH
        def only_want_v(n0, n1, vers, pth):
            if not vers.startswith("v"):
                raise ValueError("nope")

        mock_client.download_package.side_effect = only_want_v

        with create_tempdir() as path:
            dependency.fetch(path)

        calls = mock_client.download_package.call_args_list
        assert mock_client.download_package.call_count == 2
        # Show it first tried w/o v
        assert calls[0][0] == ("ApeWorX", "ApeNotAThing", "3.0.0", path)
        # The second call has the v!
        assert calls[1][0] == ("ApeWorX", "ApeNotAThing", "v3.0.0", path)

    def test_fetch_unneeded_v_prefix(self, mock_client):
        """
        Show if the version expects not to have a v-prefix but you
        provide one that it still works.
        """
        dependency = GithubDependency(
            github="ApeWorX/ApeNotAThing", version="v3.0.0", name="apetestdep"
        )
        dependency._github_client = mock_client

        # Simulate only non-v-prefix succeeding from GH
        def only_want_non_v(n0, n1, vers, pth):
            if vers.startswith("v"):
                raise ValueError("nope")

        mock_client.download_package.side_effect = only_want_non_v

        with create_tempdir() as path:
            dependency.fetch(path)

        calls = mock_client.download_package.call_args_list
        assert mock_client.download_package.call_count == 2
        # Show it first tried with the v
        assert calls[0][0] == ("ApeWorX", "ApeNotAThing", "v3.0.0", path)
        # The second call does not have the v!
        assert calls[1][0] == ("ApeWorX", "ApeNotAThing", "3.0.0", path)

    def test_fetch_given_version_when_expects_reference(self, mock_client):
        """
        Show that if a user configures `version:`, but version fails, it
        tries `ref:` instead as a backup.
        """
        dependency = GithubDependency(
            github="ApeWorX/ApeNotAThing", version="v3.0.0", name="apetestdep"
        )
        dependency._github_client = mock_client
        # Simulate no versions ever found on GH Api.
        mock_client.download_package.side_effect = ValueError("nope")

        # Simulate only the non-v prefix ref working (for a fuller flow)
        def needs_non_v_prefix_ref(n0, n1, dst_path, branch):
            # NOTE: This assertion is very important!
            #  We must only give it non-existing directories.
            assert not dst_path.is_dir()

            if branch.startswith("v"):
                raise ValueError("nope")

        mock_client.clone_repo.side_effect = needs_non_v_prefix_ref

        with create_tempdir() as path:
            dependency.fetch(path)

        calls = mock_client.clone_repo.call_args_list
        assert mock_client.clone_repo.call_count == 2
        # Show it first tried with the v
        assert calls[0][0] == ("ApeWorX", "ApeNotAThing", path)
        assert calls[0][1] == {"branch": "v3.0.0"}
        # The second call does not have the v!
        assert calls[1][0] == ("ApeWorX", "ApeNotAThing", path)
        assert calls[1][1] == {"branch": "3.0.0"}

    def test_fetch_ref(self, mock_client):
        """
        When specifying ref, it does not try version API at all.
        """
        dependency = GithubDependency(github="ApeWorX/ApeNotAThing", ref="3.0.0", name="apetestdep")
        dependency._github_client = mock_client

        with create_tempdir() as path:
            dependency.fetch(path)

        assert mock_client.download_package.call_count == 0
        mock_client.clone_repo.assert_called_once_with(
            "ApeWorX", "ApeNotAThing", path, branch="3.0.0"
        )

    def test_fetch_existing_destination_with_read_only_files(self, mock_client):
        """
        Show it handles when the destination contains read-only files already
        """
        dependency = GithubDependency(github="ApeWorX/ApeNotAThing", ref="3.0.0", name="apetestdep")
        dependency._github_client = mock_client

        with create_tempdir() as path:
            readonly_file = path / "readme.txt"
            readonly_file.write_text("readme!")

            # NOTE: This only makes a difference on Windows. If using a UNIX system,
            #   rmtree still deletes readonly files regardless. Windows is more restrictive.
            os.chmod(readonly_file, 0o444)  # Read-only permissions

            dependency.fetch(path)
            assert not readonly_file.is_file()


class TestPythonDependency:
    @pytest.fixture(scope="class", params=("site_package", "python", "pypi"))
    def python_dependency(self, request):
        return PythonDependency.model_validate({request.param: "web3"})

    def test_name(self, python_dependency):
        assert python_dependency.name == "web3"

    def test_version_id(self, python_dependency):
        actual = python_dependency.version_id
        assert isinstance(actual, str)
        assert len(actual) > 0
        assert actual[0].isnumeric()
        assert "." in actual  # sep from minor / major / patch

    def test_version_id_not_found(self):
        name = "xxthisnameisnotarealpythonpackagexx"
        dependency = PythonDependency.model_validate({"site_package": name})
        expected = rf"Dependency '{name}' not installed\. Either install or specify the `version:` to continue."
        with pytest.raises(ProjectError, match=expected):
            _ = dependency.version_id

    def test_fetch(self, python_dependency):
        with create_tempdir() as temp_dir:
            python_dependency.fetch(temp_dir)
            files = [x for x in temp_dir.iterdir()]
            assert len(files) > 0


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
        expected = f"<LocalDependency local={path}, version=1.0.0>"
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

    def test_installed(self, dependency):
        dependency.uninstall()
        assert not dependency.installed
        dependency.install()
        assert dependency.installed

    def test_installed_version_id_fails(self, project):
        api = PythonDependency(
            site_package="apethisdependencyisnotinstalled",
            name="apethisdependencyisnotinstalled",
        )
        dependency = Dependency(api, project)
        assert not dependency.installed

    def test_compile(self, project):
        with create_tempdir() as path:
            api = LocalDependency(local=path, name="ooga", version="1.0.0")
            dependency = Dependency(api, project)
            contract_path = dependency.project.contracts_folder / "CCC.json"
            contract_path.parent.mkdir(exist_ok=True, parents=True)
            contract_path.write_text(
                '[{"name":"foo","type":"fallback", "stateMutability":"nonpayable"}]',
                encoding="utf8",
            )

            # Since we are adding a file mid-session, we have to refresh so
            # it's picked up. Users typically don't have to do this.
            dependency.project.refresh_sources()

            result = dependency.compile()
            assert len(result) == 1
            assert result["CCC"].name == "CCC"

    @skip_if_plugin_installed("vyper", "solidity")
    def test_compile_missing_compilers(self, project, ape_caplog):
        with create_tempdir() as path:
            api = LocalDependency(local=path, name="ooga2", version="1.1.0")
            dependency = Dependency(api, project)
            sol_path = dependency.project.contracts_folder / "Sol.sol"
            sol_path.parent.mkdir(exist_ok=True, parents=True)
            sol_path.write_text("// Sol", encoding="utf8")
            vy_path = dependency.project.contracts_folder / "Vy.vy"
            vy_path.write_text("# Vy", encoding="utf8")
            expected = (
                "Compiling dependency produced no contract types. "
                "Try installing 'ape-solidity' or 'ape-vyper'."
            )
            result = dependency.compile()
            assert len(result) == 0
            assert expected in ape_caplog.head


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

    def test_load_contracts(self, project):
        name = "openzeppelin"
        options = project.dependencies[name]
        project = options["5.2.0"]
        # Use INFO level logging so we can still if
        # any compilers get installed.
        with logger.at_level(LogLevel.INFO):
            actual = project.load_contracts()

        assert len(actual) > 0

    def test_load_contracts_with_config_override(self, empty_project):
        # NOTE: It is important that `contracts_folder` is present in settings
        #  for this test to test against a previous bug where we got multiple values.
        override = {"contracts_folder": "src"}
        contracts_path = empty_project.path / "src"
        contracts_path.mkdir(exist_ok=True, parents=True)
        (contracts_path / "contract.json").write_text('{"abi": []}', encoding="utf8")

        data = {
            "name": "FooBar",
            "local": f"{empty_project.path}",
            "config_override": override,
        }
        empty_project.dependencies.install(**data)
        dependency = empty_project.dependencies.get("foobar", "local")
        assert dependency.config.contracts_folder == "src"

        assert empty_project.contracts_folder == empty_project.path / "src"
        assert [x.name for x in empty_project.sources.paths] == ["contract.json"]
        actual = empty_project.load_contracts()
        assert len(actual) > 0

    def test_getattr(self, project):
        """
        Access contracts using __getattr__ from the dependency's project.
        """
        name = "openzeppelin"
        oz_492 = project.dependencies.get_dependency(name, "4.9.6")
        contract = oz_492.project.AccessControl
        assert contract.contract_type.name == "AccessControl"
