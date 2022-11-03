from pathlib import Path

import pytest

from ape.pytest.fixtures import PytestApeFixtures
from tests.integration.cli.utils import skip_projects_except

BASE_PROJECTS_PATH = Path(__file__).parent / "projects"
TOKEN_B_GAS_REPORT = """
                         TokenB Gas

  Method     Times called    Min.    Max.    Mean   Median
 ──────────────────────────────────────────────────────────
  transfer              1   50911   50911   50911    50911
"""
EXPECTED_GAS_REPORT = rf"""
                      TestContractVy Gas

  Method       Times called    Min.    Max.    Mean   Median
 ────────────────────────────────────────────────────────────
  setNumber               3   51033   51033   51033    51033
  fooAndBar               1   23430   23430   23430    23430
  setAddress              1   44850   44850   44850    44850

                         TokenA Gas

  Method     Times called    Min.    Max.    Mean   Median
 ──────────────────────────────────────────────────────────
  transfer              1   50911   50911   50911    50911
{TOKEN_B_GAS_REPORT}
"""


@pytest.fixture(autouse=True)
def connection(networks):
    with networks.ethereum.local.use_default_provider():
        yield


@pytest.fixture
def setup_pytester(pytester):
    def setup(project_name: str):
        tests_path = BASE_PROJECTS_PATH / project_name / "tests"

        # Assume all tests should pass
        number_of_tests = 0
        test_files = {}
        for file_path in tests_path.iterdir():
            if file_path.name.startswith("test_") and file_path.suffix == ".py":
                content = file_path.read_text()
                test_files[file_path.name] = content
                number_of_tests += len(
                    [x for x in content.split("\n") if x.startswith("def test_")]
                )

        pytester.makepyfile(**test_files)

        # Check for a conftest.py
        conftest = tests_path / "conftest.py"
        if conftest.is_file():
            pytester.makeconftest(conftest.read_text())

        # Returns expected number of passing tests.
        return number_of_tests

    return setup


def run_gas_test(result, expected_number_passed: int, expected_report: str = EXPECTED_GAS_REPORT):
    result.assert_outcomes(passed=expected_number_passed), "\n".join(result.outlines)

    gas_header_line_index = None
    for index, line in enumerate(result.outlines):
        if "Gas Profile" in line:
            gas_header_line_index = index

    assert gas_header_line_index is not None, "'Gas Profile' not in output."
    expected = expected_report.split("\n")[1:]
    start_index = gas_header_line_index + 1
    end_index = start_index + len(expected)
    actual = [x.rstrip() for x in result.outlines[start_index:end_index]]
    assert len(actual) == len(expected)
    for actual_line, expected_line in zip(actual, expected):
        assert actual_line == expected_line


@skip_projects_except(("test", "with-contracts"))
def test_test(networks, setup_pytester, project, pytester):
    expected_test_passes = setup_pytester(project.path.name)
    result = pytester.runpytest()
    result.assert_outcomes(passed=expected_test_passes), "\n".join(result.outlines)


@skip_projects_except(("test", "with-contracts"))
def test_test_isolation_disabled(setup_pytester, project, pytester):
    # check the disable isolation option actually disables built-in isolation
    setup_pytester(project.path.name)
    result = pytester.runpytest("--disable-isolation", "--setup-show")
    assert "F _function_isolation" not in "\n".join(result.outlines)


@skip_projects_except(("test", "with-contracts"))
def test_fixture_docs(setup_pytester, project, pytester):
    result = pytester.runpytest("-q", "--fixtures")

    # 'accounts', 'networks', 'chain', and 'project' (etc.)
    fixtures = [prop for n, prop in vars(PytestApeFixtures).items() if not n.startswith("_")]
    for fixture in fixtures:
        # The doc str of the fixture shows in the CLI output
        doc_str = fixture.__doc__.strip()
        assert doc_str in "\n".join(result.outlines)


class ApeTestGethTests:
    """
    Tests using ``ape-geth`` provider. Geth supports more testing features,
    such as tracing.

    **NOTE**: These tests are placed in a class for ``pytest-xdist`` scoping reasons.
    """

    @skip_projects_except("geth")
    def test_gas_flag_in_tests(self, networks, setup_pytester, project, pytester):
        settings = {"geth": {"ethereum": {"local": {"uri": "http://127.0.0.1:5005"}}}}
        expected_test_passes = setup_pytester(project.path.name)
        with networks.ethereum.local.use_default_provider(provider_settings=settings):
            result = pytester.runpytest("--gas")
            run_gas_test(result, expected_test_passes)

    @skip_projects_except("geth")
    def test_gas_flag_set_in_config(self, setup_pytester, project, pytester, switch_config):
        expected_test_passes = setup_pytester(project.path.name)
        config_content = """
geth:
  ethereum:
    local:
      uri: http://127.0.0.1:5001

test:
  gas:
    show: true
    """

        with switch_config(project, config_content):
            result = pytester.runpytest()
            run_gas_test(result, expected_test_passes)

    @skip_projects_except("geth")
    def test_gas_flag_exclude_method_using_cli_option(self, setup_pytester, project, pytester):
        expected_test_passes = setup_pytester(project.path.name)
        line = "\n  fooAndBar               1   23430   23430   23430    23430"
        expected = EXPECTED_GAS_REPORT.replace(line, "")
        result = pytester.runpytest("--gas", "--gas-exclude", "*:fooAndBar")
        run_gas_test(result, expected_test_passes, expected_report=expected)

    @skip_projects_except("geth")
    def test_gas_flag_exclusions_set_in_config(
        self, setup_pytester, project, pytester, switch_config
    ):
        expected_test_passes = setup_pytester(project.path.name)
        line = "\n  fooAndBar               1   23430   23430   23430    23430"
        expected = EXPECTED_GAS_REPORT.replace(line, "")
        expected = expected.replace(TOKEN_B_GAS_REPORT, "")
        config_content = r"""
    geth:
      ethereum:
        local:
          uri: http://127.0.0.1:5001

    test:
      gas:
        exclude:
          - method_name: fooAndBar
          - contract_name: TokenB
    """
        with switch_config(project, config_content):
            result = pytester.runpytest("--gas")
            run_gas_test(result, expected_test_passes, expected_report=expected)

    @skip_projects_except("geth")
    def test_gas_flag_excluding_contracts(self, setup_pytester, project, pytester):
        expected_test_passes = setup_pytester(project.path.name)
        result = pytester.runpytest("--gas", "--gas-exclude", "TestContractVy,TokenA")
        run_gas_test(result, expected_test_passes, expected_report=TOKEN_B_GAS_REPORT)

    @skip_projects_except("test")
    def test_gas_flag_when_not_supported(self, setup_pytester, project, pytester):
        setup_pytester(project.path.name)
        result = pytester.runpytest("--gas")
        assert (
            "Provider 'test' does not support transaction "
            "tracing and is unable to display a gas profile"
        ) in "\n".join(result.outlines)
