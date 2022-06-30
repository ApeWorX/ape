import pytest

from .utils import skip_projects_except

projects_with_tests = skip_projects_except(["test"])


@pytest.fixture(scope="module", autouse=True)
def connection(networks):
    # Ensure we are connected in case becomes disconnected in previous test
    with networks.ethereum.local.use_provider("test"):
        yield


@projects_with_tests
def test_test(ape_cli, runner):
    # test cases implicitly test built-in isolation
    result = runner.invoke(ape_cli, ["test"])
    assert result.exit_code == 0, result.output


@projects_with_tests
def test_test_isolation_disabled(ape_cli, runner):
    # check the disable isolation option actually disables built-in isolation
    result = runner.invoke(ape_cli, ["test", "--disable-isolation", "--setup-show"])
    assert result.exit_code == 1
    assert "F _function_isolation" not in result.output


@projects_with_tests
def test_fixture_docs(ape_cli, runner):
    result = runner.invoke(ape_cli, ["test", "-q", "--fixtures"])
    assert "A collection of pre-funded accounts." in result.output
    assert (
        "Manipulate the blockchain, such as mine or change the pending timestamp." in result.output
    )
    assert "Connect to other networks in your tests." in result.output
    assert "Access contract types and dependencies." in result.output
