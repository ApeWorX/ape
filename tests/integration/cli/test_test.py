from .utils import skip_projects_except


@skip_projects_except(["test"])
def test_test(ape_cli, runner):
    result = runner.invoke(ape_cli, ["test"])
    assert result.exit_code == 0, result.output
