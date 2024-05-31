import pytest

from tests.integration.cli.utils import github_xfail, run_once

TEST_PLUGIN_NAME = "tokens"
TEST_PLUGIN_NAME_2 = "optimism"


class PluginsList(list):
    def __init__(self, header: str, lines: list[str]):
        self.header = header
        self.contains_version = len(lines[0].split(" ")) > 1 if lines else False
        names = [x.split(" ")[0].strip() for x in lines]
        super().__init__(names)


class ListResult:
    CORE_KEY = "Core Plugins"
    INSTALLED_KEY = "Installed Plugins"
    AVAILABLE_KEY = "Available Plugins"

    def __init__(self, lines: list[str]):
        self._lines = lines

    @classmethod
    def parse_output(cls, output: str) -> "ListResult":
        lines = [x.strip() for x in output.split("\n") if x.strip()]

        # Any line that may start the output
        start_lines = (
            "No plugins installed. Use '--all' to see available plugins.",
            cls.CORE_KEY,
            cls.INSTALLED_KEY,
        )
        start_index = _get_next_index(lines, start_lines)
        return ListResult(lines[start_index:])

    @property
    def core_plugins(self) -> PluginsList:
        # These tests currently always assume an installed plugins
        if self.CORE_KEY not in self._lines:
            return PluginsList(self.CORE_KEY, [])

        end_index = self._get_next_index((self.INSTALLED_KEY, self.AVAILABLE_KEY), default=1)
        plugins = _clean(self._lines[1:end_index])
        return PluginsList(self.CORE_KEY, plugins)

    @property
    def installed_plugins(self) -> PluginsList:
        if self.INSTALLED_KEY not in self._lines:
            return PluginsList(self.AVAILABLE_KEY, [])

        start = self._lines.index(self.INSTALLED_KEY) + 1
        if self.AVAILABLE_KEY in self._lines:
            end = self._lines.index(self.AVAILABLE_KEY)
        else:
            end = len(self._lines)

        plugins = _clean(self._lines[start:end])
        return PluginsList(self.INSTALLED_KEY, plugins)

    @property
    def available_plugins(self) -> PluginsList:
        if self.AVAILABLE_KEY not in self._lines:
            return PluginsList(self.AVAILABLE_KEY, [])

        start = self._lines.index(self.AVAILABLE_KEY) + 1
        plugins = _clean(self._lines[start:])
        return PluginsList(self.AVAILABLE_KEY, plugins)

    def _get_next_index(self, start_options: tuple[str, ...], default: int = 0) -> int:
        return _get_next_index(self._lines, start_options=start_options, default=default)


def _get_next_index(lines: list[str], start_options: tuple[str, ...], default: int = 0) -> int:
    for index, line in enumerate(lines):
        if line in start_options:
            return index

    return default


def _clean(lines):
    return [x for x in [x.strip() for x in lines if x]]


@pytest.fixture(scope="module")
def installed_plugin(ape_plugins_runner):
    plugin_installed = TEST_PLUGIN_NAME in ape_plugins_runner.invoke_list().installed_plugins
    did_install = False
    if not plugin_installed:
        install_result = ape_plugins_runner.invoke(
            (
                "install",
                TEST_PLUGIN_NAME,
            )
        )
        list_result = ape_plugins_runner.invoke_list()
        plugins_list_output = list_result.installed_plugins
        did_install = TEST_PLUGIN_NAME in plugins_list_output
        msg = f"Failed to install plugin necessary for tests: {install_result.output}"
        assert did_install, msg

    yield

    if did_install:
        ape_plugins_runner.invoke(("uninstall", TEST_PLUGIN_NAME))


@github_xfail()
def test_list_excludes_core_plugins(ape_plugins_runner):
    result = ape_plugins_runner.invoke_list()
    message = "{} should not be in installed plugins".format
    assert not result.core_plugins
    assert not result.available_plugins
    assert "console" not in result.installed_plugins, message("console")
    assert "networks" not in result.installed_plugins, message("networks")
    assert "node" not in result.installed_plugins, message("node")


@github_xfail()
def test_list_include_version(ape_plugins_runner, installed_plugin):
    result = ape_plugins_runner.invoke_list()
    assert result.installed_plugins.contains_version, "version is not in output"


@github_xfail()
def test_list_does_not_repeat(ape_plugins_runner, installed_plugin):
    result = ape_plugins_runner.invoke_list(("--all",))
    assert "ethereum" in result.core_plugins
    assert "ethereum" not in result.installed_plugins
    assert "ethereum" not in result.available_plugins


@pytest.mark.pip
@run_once
def test_install_upgrade(ape_plugins_runner, installed_plugin):
    result = ape_plugins_runner.invoke(("install", TEST_PLUGIN_NAME, "--upgrade"))
    assert result.exit_code == 0


@pytest.mark.pip
@run_once
def test_install_upgrade_failure(ape_plugins_runner):
    result = ape_plugins_runner.invoke(("install", "NOT_EXISTS", "--upgrade"))
    assert result.exit_code == 1


@pytest.mark.pip
@run_once
def test_install_multiple_in_one_str(ape_plugins_runner):
    result = ape_plugins_runner.invoke(("install", f"{TEST_PLUGIN_NAME} {TEST_PLUGIN_NAME_2}"))
    assert result.exit_code == 0


@pytest.mark.pip
@run_once
def test_install_from_config_file(ape_cli, runner, temp_config):
    plugins_config = {"plugins": [{"name": TEST_PLUGIN_NAME}]}
    with temp_config(plugins_config):
        result = runner.invoke(ape_cli, ("plugins", "install", "."), catch_exceptions=False)
        assert result.exit_code == 0, result.output
        assert TEST_PLUGIN_NAME in result.stdout


@pytest.mark.pip
@run_once
def test_uninstall(ape_cli, runner, installed_plugin):
    result = runner.invoke(
        ape_cli, ("plugins", "uninstall", TEST_PLUGIN_NAME, "--yes"), catch_exceptions=False
    )
    assert result.exit_code == 0, result.output
    assert TEST_PLUGIN_NAME in result.output
