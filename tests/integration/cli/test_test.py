from .utils import skip_projects_except


@skip_projects_except(["test"])
def test_test(ape_cli, runner):
    # test cases implicitly test built-in isolation
    result = runner.invoke(ape_cli, ["test"])
    assert result.exit_code == 0, result.output


@skip_projects_except(["test"])
def test_test_isolation_disabled(ape_cli, runner):
    # check the disable isolation option actually disables built-in isolation
    result = runner.invoke(ape_cli, ["test", "--disable-isolation", "--setup-show"])
    assert result.exit_code == 1
    assert "F _function_isolation" not in result.output
