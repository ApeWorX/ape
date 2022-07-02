from .utils import skip_projects_except

projects_with_tests = skip_projects_except(["test"])


@projects_with_tests
def test_test(ape_cli, runner, project):
    # test cases implicitly test built-in isolation

    result = runner.invoke(ape_cli, ["test"])
    assert result.exit_code == 0, result.output


@projects_with_tests
def test_test_isolation_disabled(ape_cli, runner, project):
    # check the disable isolation option actually disables built-in isolation
    result = runner.invoke(ape_cli, ["test", "--disable-isolation", "--setup-show"])
    assert result.exit_code == 1
    assert "F _function_isolation" not in result.output


@projects_with_tests
def test_fixture_docs(ape_cli, runner, project):
    result = runner.invoke(ape_cli, ["test", "-q", "--fixtures"])
    assert "A collection of pre-funded accounts." in result.output
    assert (
        "Manipulate the blockchain, such as mine or change the pending timestamp." in result.output
    )
    assert "Connect to other networks in your tests." in result.output
    assert "Access contract types and dependencies." in result.output
