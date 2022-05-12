import pytest

from tests.integration.cli.utils import skip_projects_except

TEST_PLUGIN_NAME = "tokens"


def plugins_xfail():
    """
    Currently, there are two reasons we know these tests will fail.

    1. GitHub rate limiting issues
    2. Unable to figure out how to properly install a python package while python is running.
    """

    def wrapper(f):
        f = pytest.mark.xfail(
            strict=False, reason="Github rate limiting issues or plugin install issues"
        )(f)
        f = skip_projects_except(["test"])(f)
        return f

    return wrapper


@plugins_xfail()
def test_list_excludes_core_plugins(ape_cli, runner):
    result = runner.invoke(ape_cli, ["plugins", "list"])
    assert result.exit_code == 0, result.output
    assert "console" not in result.output, "console is not supposed to be in Installed Plugins"
    assert "networks" not in result.output, "networks is not supposed to be in Installed Plugins"
    assert "geth" not in result.output, "networks is not supposed to be in Installed Plugins"


@plugins_xfail()
def test_list_include_version(ape_cli, runner):
    # TODO: Figure out how to install plugin prior to test.
    result = runner.invoke(ape_cli, ["plugins", "list"])
    assert result.exit_code == 0, result.output
    assert "0.1" in result.output, "version is not in output"


@plugins_xfail()
def test_list_does_not_repeat(ape_cli, runner):
    # TODO: Figure out how to install plugin prior to test.
    result = runner.invoke(ape_cli, ["plugins", "list", "--all"])
    sections = result.output.split("\n\n")
    assert "tokens" in sections[1]
    assert "tokens" not in sections[0]
    assert "tokens" not in sections[2]
