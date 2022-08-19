from typing import List, Optional

import pytest

from tests.integration.cli.utils import run_once

TEST_PLUGIN_NAME = "tokens"


class PluginsList(list):
    def __init__(self, header: str, lines: List[str]):
        self.header = header
        self.contains_version = len(lines[0].split(" ")) > 1 if lines else False
        names = [x.split(" ")[0].strip() for x in lines]
        super().__init__(names)


class ListResult:
    CORE_KEY = "Installed Core Plugins:"
    INSTALLED_KEY = "Installed Plugins:"
    AVAILABLE_KEY = "Available Plugins:"

    def __init__(self, output):
        self._output = output

    @property
    def _lines(self) -> List[str]:
        return self._output.split("\n")

    @property
    def core_plugins(self) -> PluginsList:
        # These tests currently always assume an installed plugins
        if self.INSTALLED_KEY not in self._lines:
            return PluginsList(self.CORE_KEY, [])

        installed_index = self._lines.index(self.INSTALLED_KEY)
        plugins = _clean(self._lines[1:installed_index])
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


def _clean(lines):
    return [x for x in [x.strip() for x in lines if x]]


@pytest.fixture(scope="module")
def ape_plugins_runner(subprocess_runner_cls):
    """
    Use subprocess runner so can manipulate site packages and see results.
    """

    class PluginSubprocessRunner(subprocess_runner_cls):
        def __init__(self):
            super().__init__(["plugins"])

        def invoke_list(self, arguments: Optional[List] = None):
            arguments = arguments or []
            result = self.invoke(["list", *arguments])
            assert result.exit_code == 0
            return ListResult(result.output)

    return PluginSubprocessRunner()


def plugins_xfail():
    """
    Currently, there are two reasons we know these tests will fail.

    1. GitHub rate limiting issues
    """

    def wrapper(f):
        f = pytest.mark.xfail(
            strict=False, reason="Github rate limiting issues or plugin install issues"
        )(f)
        f = run_once(f)
        return f

    return wrapper


@pytest.fixture(scope="module")
def installed_plugin(ape_plugins_runner):
    plugin_installed = TEST_PLUGIN_NAME in ape_plugins_runner.invoke_list().installed_plugins
    did_install = False
    if not plugin_installed:
        ape_plugins_runner.invoke(["install", TEST_PLUGIN_NAME])
        plugins_list_output = ape_plugins_runner.invoke_list().installed_plugins
        did_install = TEST_PLUGIN_NAME in plugins_list_output
        assert did_install, "Failed to install plugin necessary for tests"

    yield

    if did_install:
        ape_plugins_runner.invoke(["uninstall", TEST_PLUGIN_NAME])


@plugins_xfail()
def test_list_excludes_core_plugins(ape_plugins_runner):
    result = ape_plugins_runner.invoke_list()
    msg = "{} should not be in installed plugins".format
    assert not result.core_plugins
    assert not result.available_plugins
    assert "console" not in result.installed_plugins, msg("console")
    assert "networks" not in result.installed_plugins, msg("networks")
    assert "geth" not in result.installed_plugins, msg("geth")


@plugins_xfail()
def test_list_include_version(ape_plugins_runner, installed_plugin):
    result = ape_plugins_runner.invoke_list()
    assert result.installed_plugins.contains_version, "version is not in output"


@plugins_xfail()
def test_list_does_not_repeat(ape_plugins_runner, installed_plugin):
    result = ape_plugins_runner.invoke_list(["--all"])
    assert "ethereum" in result.core_plugins
    assert "ethereum" not in result.installed_plugins
    assert "ethereum" not in result.available_plugins


@plugins_xfail()
def test_upgrade(ape_plugins_runner, installed_plugin):
    result = ape_plugins_runner.invoke(["install", TEST_PLUGIN_NAME, "--upgrade"])
    assert result.exit_code == 0


@plugins_xfail()
def test_upgrade_failure(ape_plugins_runner):
    result = ape_plugins_runner.invoke(["install", "NOT_EXISTS", "--upgrade"])
    assert result.exit_code == 1
