import pytest

from tests.integration.cli.utils import skip_projects_except


@pytest.mark.xfail(strict=False, reason="Github rate limiting issues")
@skip_projects_except(["test"])  # Only run on single project to prevent rate-limiting in CI/CD
def test_list_excludes_core_plugins(ape_cli, runner):
    result = runner.invoke(ape_cli, ["plugins", "list"])
    assert result.exit_code == 0, result.output
    assert "console" not in result.output, "console is not supposed to be in Installed Plugins"
    assert "networks" not in result.output, "networks is not supposed to be in Installed Plugins"
    assert "geth" not in result.output, "networks is not supposed to be in Installed Plugins"


@pytest.mark.xfail(strict=False, reason="Requires plugins installed")
@skip_projects_except(["test"])  # Only run on single project to prevent rate-limiting in CI/CD
def test_list_include_version(ape_cli, runner):
    result = runner.invoke(ape_cli, ["plugins", "list"])
    assert result.exit_code == 0, result.output
    assert "0.1" in result.output, "version is not in output"
