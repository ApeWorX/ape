from unittest import mock

import pytest

from ape.api import TransactionAPI
from ape.exceptions import PluginVersionError
from ape.logging import LogLevel
from ape.managers.plugins import _get_unimplemented_methods_warning
from ape.plugins._utils import CORE_PLUGINS as CORE_PLUGINS_LIST
from ape.plugins._utils import (
    ApePluginsRepr,
    ModifyPluginResultHandler,
    PluginGroup,
    PluginMetadata,
    PluginMetadataList,
    PluginType,
    _filter_plugins_from_dists,
    ape_version,
)

CORE_PLUGINS = ("run",)
AVAILABLE_PLUGINS = ("available", "installed")
INSTALLED_PLUGINS = ("installed", "thirdparty")
THIRD_PARTY = ("thirdparty",)


mark_specifiers_less_than_ape = pytest.mark.parametrize(
    "specifier",
    (f"<{ape_version[0]}", f">0.1,<{ape_version[0]}", f"==0.{int(ape_version[2]) - 1}"),
)
parametrize_pip_cmd = pytest.mark.parametrize(
    "pip_command", [["python", "-m", "pip"], ["uv", "pip"]]
)


@pytest.fixture(autouse=True)
def get_dists_patch(mocker):
    return mocker.patch("ape.plugins._utils._get_distributions")


@pytest.fixture
def make_dist(mocker):
    def fn(name, version):
        mock_dist = mocker.MagicMock()
        mock_dist.name = name
        mock_dist.version = version
        return mock_dist

    return fn


@pytest.fixture(autouse=True)
def mock_installed_packages(make_dist, get_dists_patch):
    def fn(version: str):
        get_dists_patch.return_value = (
            make_dist("FOOFOO", "1.1.1"),
            make_dist(f"ape-{INSTALLED_PLUGINS[0]}", version),
            make_dist("aiohttp", "3.8.5"),
            make_dist(f"ape-{THIRD_PARTY[0]}", version),
        )
        return get_dists_patch

    return fn


@pytest.fixture(autouse=True)
def plugin_test_env(mocker, mock_installed_packages):
    root = "ape.plugins._utils"

    # Prevent calling out to GitHub
    gh_mock = mocker.patch(f"{root}._get_available_plugins")
    gh_mock.return_value = {f"ape_{x}" for x in AVAILABLE_PLUGINS}

    mock_installed_packages(ape_version.base)


@pytest.fixture
def package_names() -> set[str]:
    return {
        f"ape-{x}" for x in [*CORE_PLUGINS, *AVAILABLE_PLUGINS, *INSTALLED_PLUGINS, *THIRD_PARTY]
    }


@pytest.fixture
def plugin_metadata(package_names) -> PluginMetadataList:
    names = {x for x in package_names}
    names.remove("ape-installed")
    names.add(f"ape-installed==0.{ape_version.minor}.0")
    names.remove("ape-thirdparty")
    names.add(f"ape-thirdparty==0.{ape_version.minor}.0")
    return PluginMetadataList.from_package_names(names)


class TestPluginMetadataList:
    def test_from_package_names(self, plugin_metadata):
        actual = plugin_metadata
        assert actual.core.plugin_names == list(CORE_PLUGINS)
        assert actual.third_party.plugin_names == list(THIRD_PARTY)
        assert actual.installed.plugin_names == [INSTALLED_PLUGINS[0]]  # Not 3rd party
        assert actual.available.plugin_names == [AVAILABLE_PLUGINS[0]]  # Not installed

    def test_all_plugins(self, plugin_metadata, package_names):
        actual = {f"ape-{x.name}" for x in plugin_metadata.all_plugins}
        assert actual == package_names


class TestPluginMetadata:
    @pytest.mark.parametrize(
        "name", ("ape-foo-bar", "ape-foo-bar", "ape_foo_bar", "foo-bar", "foo_bar")
    )
    def test_names(self, name):
        metadata = PluginMetadata(name=name)
        assert metadata.name == "foo-bar"
        assert metadata.package_name == "ape-foo-bar"
        assert metadata.module_name == "ape_foo_bar"

    def test_model_validator_when_version_included_with_name(self):
        # This allows parsing requirements files easier
        metadata = PluginMetadata(name=f"ape-foo-bar==0.{ape_version.minor}.0")
        assert metadata.name == "foo-bar"
        assert metadata.version == f"==0.{ape_version.minor}.0"

    @pytest.mark.parametrize(
        "version",
        (f"0.{ape_version.minor}.0", f"v0.{ape_version.minor}.0", f"0.{ape_version.minor}.0a123"),
    )
    def test_version(self, version):
        metadata = PluginMetadata(name="foo", version=version)
        assert metadata.version == version

    def test_install_str_without_version(self):
        metadata = PluginMetadata(name="foo-bar")
        actual = metadata.install_str
        expected_version = f">=0.{ape_version.minor},<0.{ape_version.minor + 1}"
        assert actual == f"ape-foo-bar{expected_version}"

    def test_install_str_with_version(self):
        metadata = PluginMetadata(name="foo-bar", version=f"0.{ape_version.minor}.0")
        actual = metadata.install_str
        assert actual == f"ape-foo-bar==0.{ape_version.minor}.0"

    def test_install_str_with_complex_constraint(self):
        metadata = PluginMetadata(
            name="foo", version=f">=0.{ape_version.minor}.0,<0.{ape_version.minor + 1}.0"
        )
        actual = metadata.install_str
        assert actual == f"ape-foo>=0.{ape_version.minor}.0,<0.{ape_version.minor + 1}.0"

    def test_install_str_with_complex_constraint_in_name(self):
        metadata = PluginMetadata(name=f"foo>=0.{ape_version.minor}.0,<0.{ape_version.minor + 1}.0")
        actual = metadata.install_str
        assert actual == f"ape-foo>=0.{ape_version.minor}.0,<0.{ape_version.minor + 1}.0"

    def test_install_str_when_using_git_remote(self):
        url = "git+https://example.com/myorg/ape-foo.git@branch_name"
        metadata = PluginMetadata(name="foo", version=url)
        assert metadata.name == "foo"
        actual = metadata.install_str
        assert actual == url

    def test_install_str_remote_in_name(self):
        url = "git+https://example.com/myorg/ape-foo.git@branch_name"
        metadata = PluginMetadata(name=f"foo@{url}")
        assert metadata.name == "foo"
        actual = metadata.install_str
        assert actual == url

    def test_install_str_only_remote(self):
        url = "git+https://example.com/myorg/ape-foo.git@branch_name"
        metadata = PluginMetadata(name=url)
        actual = metadata.install_str
        assert actual == url
        assert metadata.name == "foo"

    def test_is_available(self):
        metadata = PluginMetadata(name=list(AVAILABLE_PLUGINS)[0])
        assert metadata.is_available
        metadata = PluginMetadata(name="foobar")
        assert not metadata.is_available

    @parametrize_pip_cmd
    def test_prepare_install(self, pip_command):
        metadata = PluginMetadata(name=list(AVAILABLE_PLUGINS)[0], pip_command=pip_command)
        actual = metadata._prepare_install(skip_confirmation=True)
        assert actual is not None
        arguments = actual.get("args", [])
        shared = [
            "pip",
            "install",
            f"ape-available>=0.{ape_version.minor},<0.{ape_version.minor + 1}",
            "--quiet",
        ]
        if arguments[0] == "uv":
            expected = ["uv", *shared]
            assert arguments == expected
        else:
            expected = ["-m", *shared]
            assert "python" in arguments[0]
            assert arguments[1:] == expected

    @parametrize_pip_cmd
    def test_prepare_install_upgrade(self, pip_command):
        metadata = PluginMetadata(name=list(AVAILABLE_PLUGINS)[0], pip_command=pip_command)
        actual = metadata._prepare_install(upgrade=True, skip_confirmation=True)
        assert actual is not None
        arguments = actual.get("args", [])
        shared = [
            "pip",
            "install",
            "--upgrade",
            f"ape-available>=0.{ape_version.minor},<0.{ape_version.minor + 1}",
            "--quiet",
        ]

        if pip_command[0].startswith("uv"):
            expected = ["uv", *shared]
            assert arguments == expected

        else:
            expected = ["-m", *shared]
            assert "python" in arguments[0]
            assert arguments[1:] == expected

    @mark_specifiers_less_than_ape
    def test_prepare_install_version_smaller_than_ape(self, specifier, ape_caplog):
        metadata = PluginMetadata(name=list(AVAILABLE_PLUGINS)[0], version=specifier)
        expected = (
            r"Unable to install plugin\.\n"
            r"Reason: Doing so will downgrade Ape's version\.\n"
            r"To resolve: Downgrade Ape first\."
        )
        with pytest.raises(PluginVersionError, match=expected):
            metadata._prepare_install(skip_confirmation=True)

    def test_check_installed_python_39(self, mocker, get_dists_patch):
        mock_dist = mocker.MagicMock()
        get_dists_patch.return_value = [mock_dist]
        mock_dist.name = ""
        mock_dist.metadata = {"Name": "ape-py39plugin"}

        metadata = PluginMetadata(name="py39plugin")

        # If the next line doesn't fail, the test passed.
        # This triggers looping through the dist w/o a name attr.
        assert metadata.check_installed()

    @pytest.mark.parametrize(
        "plugin,expected", [(list(INSTALLED_PLUGINS)[0], True), (list(AVAILABLE_PLUGINS)[0], False)]
    )
    def test_check_installed_python_310_or_greater(self, plugin, expected):
        installed = PluginMetadata(name=plugin)
        assert installed.check_installed() is expected

    @parametrize_pip_cmd
    def test_get_uninstall_args(self, pip_command):
        metadata = PluginMetadata(name="dontmatter", pip_command=pip_command)
        arguments = metadata._get_uninstall_args()
        pip_cmd_len = len(metadata.pip_command)

        for idx, pip_pt in enumerate(pip_command):
            assert arguments[idx] == pip_pt

        expected = ["uninstall"]
        if pip_command[0] == "python":
            expected.append("-y")

        expected.extend(("ape-dontmatter", "--quiet"))
        assert arguments[pip_cmd_len:] == expected


class TestApePluginsRepr:
    def test_str(self, plugin_metadata):
        representation = ApePluginsRepr(plugin_metadata)
        actual = str(representation)
        expected = f"""
Installed Plugins
  installed     {ape_version.base}

Third-party Plugins
  thirdparty    {ape_version.base}
        """
        assert actual == expected.strip()

    def test_str_all_types(self, plugin_metadata):
        representation = ApePluginsRepr(plugin_metadata, include=list(PluginType))
        actual = str(representation)
        expected = f"""
Core Plugins
  run

Installed Plugins
  installed     {ape_version.base}

Third-party Plugins
  thirdparty    {ape_version.base}

Available Plugins
  available
        """
        assert actual == expected.strip()

    def test_str_no_plugins(self):
        plugins = PluginMetadataList.from_package_names([])
        representation = ApePluginsRepr(plugins)
        assert str(representation) == ""


class TestPluginGroup:
    def test_name(self):
        group = PluginGroup(plugin_type=PluginType.INSTALLED)
        assert group.name == "Installed"

    def test_name_when_plugin_type_is_str(self):
        group = PluginGroup(plugin_type=PluginType.INSTALLED)
        group.plugin_type = PluginType.INSTALLED.value  # type: ignore[assignment]
        assert group.name == "Installed"

    def test_repr(self):
        group = PluginGroup(plugin_type=PluginType.INSTALLED)
        assert repr(group) == "<Installed Plugins Group>"

    def test_repr_when_plugin_type_is_str(self):
        group = PluginGroup(plugin_type=PluginType.INSTALLED)
        group.plugin_type = PluginType.INSTALLED.value  # type: ignore[assignment]
        assert repr(group) == "<Installed Plugins Group>"

    def test_repr_when_exception(self, mocker):
        """
        Exceptions CANNOT happen in a repr!
        """
        patch = mocker.patch("ape.plugins._utils.PluginGroup.name", new_callable=mock.PropertyMock)
        patch.side_effect = ValueError("repr fail test")
        group = PluginGroup(plugin_type=PluginType.INSTALLED)

        assert repr(group) == "<PluginGroup>"


def test_handle_upgrade_result_when_upgrading_to_same_version(ape_caplog, logger):
    plugin = PluginMetadata(name=THIRD_PARTY[0], version=f"0.{ape_version.minor}.0")
    handler = ModifyPluginResultHandler(plugin)
    ape_caplog.set_levels(LogLevel.INFO)
    handler.handle_upgrade_result(0, f"0.{ape_version.minor}.0")
    assert f"'{THIRD_PARTY[0]}' already has version '0.{ape_version.minor}.0'" in ape_caplog.head


class TestApeVersion:
    def test_version_range(self):
        actual = ape_version.version_range
        expected = f">=0.{ape_version[2]},<0.{int(ape_version[2]) + 1}"
        assert actual == expected

    def test_next_version_range(self):
        actual = ape_version.next_version_range
        expected = f">=0.{int(ape_version[2]) + 1},<0.{int(ape_version[2]) + 2}"
        assert actual == expected

    def test_previous_version_range(self):
        actual = ape_version.previous_version_range
        expected = f">=0.{int(ape_version[2]) - 2},<0.{int(ape_version[2]) - 1}"
        assert actual == expected

    @mark_specifiers_less_than_ape
    def test_would_be_downgraded(self, specifier):
        assert ape_version.would_get_downgraded(specifier)


def test_filter_plugins_from_dists_py39(mocker):
    def make_dist(name: str):
        mock_dist = mocker.MagicMock()
        mock_dist.name = ""
        mock_dist.metadata = {"Name": f"ape-{name}"}
        return mock_dist

    plugins = [make_dist("solidity"), make_dist("vyper"), make_dist("optimism")]
    actual = set(_filter_plugins_from_dists(plugins))
    expected = {"ape-solidity", "ape-vyper", "ape-optimism"}
    assert actual == expected


def test_filter_plugins_from_dists_py310_and_greater(mocker):
    def make_dist(name: str):
        mock_dist = mocker.MagicMock()
        mock_dist.name = f"ape-{name}"
        return mock_dist

    plugins = [make_dist("solidity"), make_dist("vyper"), make_dist("optimism")]
    actual = set(_filter_plugins_from_dists(plugins))
    expected = {"ape-solidity", "ape-vyper", "ape-optimism"}
    assert actual == expected


@pytest.mark.parametrize("abstract_methods", [("method1", "method2"), {"method1": 0, "method2": 0}])
def test_get_unimplemented_methods_warning_list_containing_plugin(abstract_methods):
    plugin_registration = ("foo", "bar", TransactionAPI)
    actual = _get_unimplemented_methods_warning(plugin_registration, "p1")
    expected = (
        "'TransactionAPI' from 'p1' is not fully implemented. "
        "Remaining abstract methods: 'serialize_transaction, txn_hash'."
    )
    assert actual == expected


def test_core_plugins():
    # In case any of these happen to be installed, and this feature
    # is broken, it will fail. If none are installed, the test will always pass.
    non_core_plugins = ("ape_arbitrum", "ape_vyper", "ape_solidity", "ape_ens")
    assert not any(p in CORE_PLUGINS_LIST for p in non_core_plugins)
    assert "ape_ethereum" in CORE_PLUGINS_LIST
