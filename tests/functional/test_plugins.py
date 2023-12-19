from typing import Set
from unittest import mock

import pytest

from ape_plugins.utils import (
    ApePluginsRepr,
    ModifyPluginResultHandler,
    PluginGroup,
    PluginMetadata,
    PluginMetadataList,
    PluginType,
    _PipFreeze,
)

CORE_PLUGINS = ("run",)
AVAILABLE_PLUGINS = ("available", "installed")
INSTALLED_PLUGINS = ("installed", "thirdparty")
THIRD_PARTY = ("thirdparty",)
VERSION = "0.7.0"


def get_pip_freeze_output(version: str):
    return f"FOOFOO==1.1.1\n-e git+ssh://git@github.com/ApeWorX/ape-{INSTALLED_PLUGINS[0]}.git@aaaaaaaabbbbbb3343#egg=ape-{INSTALLED_PLUGINS[0]}\naiohttp==3.8.5\nape-{THIRD_PARTY[0]}=={version}\n"  # noqa: E501


@pytest.fixture(autouse=True)
def mock_pip_freeze(mocker):
    def fn(version: str):
        patch = mocker.patch("ape_plugins.utils._check_pip_freeze")
        patch.return_value = get_pip_freeze_output(version)
        return patch

    return fn


@pytest.fixture(autouse=True)
def plugin_test_env(mocker, mock_pip_freeze):
    root = "ape_plugins.utils"

    # Prevent calling out to GitHub
    gh_mock = mocker.patch(f"{root}._get_available_plugins")
    gh_mock.return_value = {f"ape_{x}" for x in AVAILABLE_PLUGINS}

    # Used when testing PipFreeze object itself but also extra avoids
    # actually calling out pip ever in tests.
    mock_pip_freeze(VERSION)

    # Prevent requiring plugins to be installed.
    installed_mock = mocker.patch(f"{root}._pip_freeze_plugins")
    installed_mock.return_value = {
        f"ape-{INSTALLED_PLUGINS[0]}",
        f"ape-{INSTALLED_PLUGINS[1]}=={VERSION}",
    }

    # Prevent version lookups.
    version_mock = mocker.patch(f"{root}.get_package_version")
    version_mock.return_value = VERSION


@pytest.fixture
def package_names() -> Set[str]:
    return {
        f"ape-{x}" for x in [*CORE_PLUGINS, *AVAILABLE_PLUGINS, *INSTALLED_PLUGINS, *THIRD_PARTY]
    }


@pytest.fixture
def plugin_metadata(package_names) -> PluginMetadataList:
    return PluginMetadataList.from_package_names(package_names)


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
        metadata = PluginMetadata(name="ape-foo-bar==0.7.0")
        assert metadata.name == "foo-bar"
        assert metadata.version == "==0.7.0"

    @pytest.mark.parametrize("version", ("0.7.0", "v0.7.0", "0.7.0a123"))
    def test_version(self, version):
        metadata = PluginMetadata(name="foo", version=version)
        assert metadata.version == version

    def test_install_str_without_version(self):
        metadata = PluginMetadata(name="foo-bar")
        actual = metadata.install_str
        assert actual == "ape-foo-bar"

    def test_install_str_with_version(self):
        metadata = PluginMetadata(name="foo-bar", version="0.7.0")
        actual = metadata.install_str
        assert actual == "ape-foo-bar==0.7.0"

    def test_install_str_with_complex_constraint(self):
        metadata = PluginMetadata(name="foo", version=">=0.7.0,<0.8.0")
        actual = metadata.install_str
        assert actual == "ape-foo>=0.7.0,<0.8.0"

    def test_install_str_with_complex_constraint_in_name(self):
        metadata = PluginMetadata(name="foo>=0.7.0,<0.8.0")
        actual = metadata.install_str
        assert actual == "ape-foo>=0.7.0,<0.8.0"

    def test_install_str_when_using_git_remote(self):
        url = "git+https://example.com/ape-foo/branch"
        metadata = PluginMetadata(name="foo", version=url)
        actual = metadata.install_str
        assert actual == url

    def test_install_str_remote_in_name(self):
        url = "git+https://example.com/ape-foo/branch"
        metadata = PluginMetadata(name=f"foo@{url}")
        actual = metadata.install_str
        assert actual == url

    def test_is_available(self):
        metadata = PluginMetadata(name=list(AVAILABLE_PLUGINS)[0])
        assert metadata.is_available
        metadata = PluginMetadata(name="foobar")
        assert not metadata.is_available


class TestApePluginsRepr:
    def test_str(self, plugin_metadata):
        representation = ApePluginsRepr(plugin_metadata)
        actual = str(representation)
        expected = f"""
Installed Plugins
  installed     {VERSION}

Third-party Plugins
  thirdparty    {VERSION}
        """
        assert actual == expected.strip()

    def test_str_all_types(self, plugin_metadata):
        representation = ApePluginsRepr(plugin_metadata, include=list(PluginType))
        actual = str(representation)
        expected = f"""
Core Plugins
  run

Installed Plugins
  installed     {VERSION}

Third-party Plugins
  thirdparty    {VERSION}

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
        patch = mocker.patch("ape_plugins.utils.PluginGroup.name", new_callable=mock.PropertyMock)
        patch.side_effect = ValueError("repr fail test")
        group = PluginGroup(plugin_type=PluginType.INSTALLED)

        assert repr(group) == "<PluginGroup>"


def test_pip_freeze_includes_version_when_available():
    pip_freeze = _PipFreeze()
    actual = pip_freeze.get_plugins()
    expected = {f"ape-{INSTALLED_PLUGINS[0]}", f"ape-{THIRD_PARTY[0]}==0.7.0"}
    assert actual == expected


def test_handle_upgrade_result_when_upgrading_to_same_version(caplog, logger):
    # NOTE: pip freeze mock also returns version 0.7.0 (so upgrade to same).
    logger.set_level("INFO")  # Required for test.
    plugin = PluginMetadata(name=THIRD_PARTY[0])
    handler = ModifyPluginResultHandler(plugin)
    handler.handle_upgrade_result(0, "0.7.0")
    if records := caplog.records:
        assert f"'{THIRD_PARTY[0]}' already has version '0.7.0'" in records[-1].message
    else:
        version_at_end = plugin.pip_freeze_version
        pytest.fail(
            "Missing logs when upgrading to same version 0.7.0. "
            f"pip_freeze_version={version_at_end}"
        )


def test_handle_upgrade_result_when_no_pip_freeze_version_does_not_log(caplog):
    plugin_no_version = INSTALLED_PLUGINS[0]  # Version not in pip-freeze
    plugin = PluginMetadata(name=plugin_no_version)
    handler = ModifyPluginResultHandler(plugin)
    handler.handle_upgrade_result(0, "0.7.0")

    log_parts = ("already has version", "already up to date")
    messages = [x.message for x in caplog.records]
    for message in messages:
        for pt in log_parts:
            assert pt not in message
