from .utils import skip_projects_except


@skip_projects_except(["test"])
def test_test(ape_cli, runner):
    result = runner.invoke_using_test_network(ape_cli, ["test"])
    assert result.exit_code == 0
