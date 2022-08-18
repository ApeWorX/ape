import pytest

from .utils import skip_projects_except

projects_with_tests = skip_projects_except(["test", "with-contracts"])


@pytest.fixture
def ape_test_runner(subprocess_runner_cls):
    return subprocess_runner_cls(["test"])


@pytest.fixture(autouse=True, scope="module")
def reset_provider(eth_tester_provider):
    eth_tester_provider.disconnect()
    eth_tester_provider.connect()


@projects_with_tests
def test_test(ape_test_runner, project):
    # test cases implicitly test built-in isolation
    result = ape_test_runner.invoke()
    assert result.exit_code == 0, result.output


@projects_with_tests
def test_test_isolation_disabled(ape_test_runner, project):
    # check the disable isolation option actually disables built-in isolation
    result = ape_test_runner.invoke(["--disable-isolation", "--setup-show"])
    assert result.exit_code == (1 if project.path.name == "test" else 0)
    assert "F _function_isolation" not in result.output


@projects_with_tests
def test_fixture_docs(ape_test_runner, project):
    result = ape_test_runner.invoke(["-q", "--fixtures"])
    assert "A collection of pre-funded accounts." in result.output
    assert (
        "Manipulate the blockchain, such as mine or change the pending timestamp." in result.output
    )
    assert "Connect to other networks in your tests." in result.output
    assert "Access contract types and dependencies." in result.output
