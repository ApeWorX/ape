import re
from pathlib import Path

import pytest

from ape.pytest.fixtures import PytestApeFixtures
from tests.conftest import GETH_URI, geth_process_test
from tests.integration.cli.utils import skip_projects_except

BASE_PROJECTS_PATH = Path(__file__).parent / "projects"
TOKEN_B_GAS_REPORT = r"""
 +TokenB Gas

  Method +Times called +Min. +Max. +Mean +Median
 ─+
  balanceOf +\d +\d+ + \d+ + \d+ + \d+
  transfer +\d +\d+ + \d+ + \d+ + \d+
"""
EXPECTED_GAS_REPORT = rf"""
 +TestContractVy Gas

  Method +Times called +Min. +Max. +Mean +Median
 ─+
  myNumber +\d +\d+ + \d+ + \d+ + \d+
  setNumber +\d +\d+ + \d+ + \d+ + \d+
  fooAndBar +\d +\d+ + \d+ + \d+ + \d+
  setAddress +\d +\d+ + \d+ + \d+ + \d+

 +TokenA Gas

  Method +Times called +Min. +Max. +Mean +Median
 ─+
  balanceOf +\d +\d+ + \d+ + \d+ + \d+
  transfer +\d +\d+ + \d+ + \d+ + \d+
{TOKEN_B_GAS_REPORT}
"""
GETH_LOCAL_CONFIG = f"""
geth:
  ethereum:
    local:
      uri: {GETH_URI}
"""


def filter_expected_methods(*methods_to_remove: str) -> str:
    expected = EXPECTED_GAS_REPORT
    for name in methods_to_remove:
        line = f"\n  {name} +\\d +\\d+ + \\d+ + \\d+ + \\d+"
        expected = expected.replace(line, "")

    return expected


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
    assert "WARNING: No gas usage data found." not in actual, "Gas data missing!"

    actual_len = len(actual)
    expected_len = len(expected)

    if actual_len > expected_len:
        remainder = "\n".join(actual[expected_len:])
        pytest.fail(f"Actual contains more than expected:\n{remainder}")
    elif expected_len > actual_len:
        remainder = "\n".join(expected[actual_len:])
        pytest.fail(f"Expected contains more than actual:\n{remainder}")

    for actual_line, expected_line in zip(actual, expected):
        message = f"'{actual_line}' does not match pattern '{expected_line}'."
        assert re.match(expected_line, actual_line), message


@skip_projects_except("test", "with-contracts")
def test_test(networks, setup_pytester, project, pytester, eth_tester_provider):
    _ = eth_tester_provider  # Ensure using EthTester for this test.
    expected_test_passes = setup_pytester(project.path.name)
    result = pytester.runpytest()
    result.assert_outcomes(passed=expected_test_passes), "\n".join(result.outlines)


@skip_projects_except("test", "with-contracts")
def test_test_isolation_disabled(setup_pytester, project, pytester, eth_tester_provider):
    # check the disable isolation option actually disables built-in isolation
    _ = eth_tester_provider  # Ensure using EthTester for this test.
    setup_pytester(project.path.name)
    result = pytester.runpytest("--disable-isolation", "--setup-show")
    assert "F _function_isolation" not in "\n".join(result.outlines)


@skip_projects_except("test", "with-contracts")
def test_fixture_docs(setup_pytester, project, pytester, eth_tester_provider):
    _ = eth_tester_provider  # Ensure using EthTester for this test.
    result = pytester.runpytest("-q", "--fixtures")

    # 'accounts', 'networks', 'chain', and 'project' (etc.)
    fixtures = [prop for n, prop in vars(PytestApeFixtures).items() if not n.startswith("_")]
    for fixture in fixtures:
        # The doc str of the fixture shows in the CLI output
        doc_str = fixture.__doc__.strip()
        assert doc_str in "\n".join(result.outlines)


@skip_projects_except("test")
def test_gas_flag_when_not_supported(setup_pytester, project, pytester, eth_tester_provider):
    _ = eth_tester_provider  # Ensure using EthTester for this test.
    setup_pytester(project.path.name)
    result = pytester.runpytest("--gas")
    assert (
        "Provider 'test' does not support transaction "
        "tracing and is unable to display a gas profile"
    ) in "\n".join(result.outlines)


@geth_process_test
@skip_projects_except("geth")
def test_gas_flag_in_tests(geth_provider, setup_pytester, project, pytester):
    expected_test_passes = setup_pytester(project.path.name)
    result = pytester.runpytest("--gas")
    run_gas_test(result, expected_test_passes)


@geth_process_test
@skip_projects_except("geth")
def test_gas_flag_set_in_config(geth_provider, setup_pytester, project, pytester, switch_config):
    expected_test_passes = setup_pytester(project.path.name)
    config_content = f"""
    geth:
      ethereum:
        local:
          uri: {GETH_URI}

    test:
      disconnect_providers_after: false
      gas:
        show: true
    """

    with switch_config(project, config_content):
        result = pytester.runpytest()
        run_gas_test(result, expected_test_passes)


@geth_process_test
@skip_projects_except("geth")
def test_gas_flag_exclude_using_cli_option(geth_provider, setup_pytester, project, pytester):
    expected_test_passes = setup_pytester(project.path.name)
    # NOTE: Includes both a mutable and a view method.
    expected = filter_expected_methods("fooAndBar", "myNumber")
    # Also ensure can filter out whole class
    expected = expected.replace(TOKEN_B_GAS_REPORT, "")
    result = pytester.runpytest("--gas", "--gas-exclude", "*:fooAndBar,*:myNumber,tokenB:*")
    run_gas_test(result, expected_test_passes, expected_report=expected)


@geth_process_test
@skip_projects_except("geth")
def test_gas_flag_exclusions_set_in_config(
    geth_provider, setup_pytester, project, pytester, switch_config
):
    expected_test_passes = setup_pytester(project.path.name)
    # NOTE: Includes both a mutable and a view method.
    expected = filter_expected_methods("fooAndBar", "myNumber")
    # Also ensure can filter out whole class
    expected = expected.replace(TOKEN_B_GAS_REPORT, "")
    config_content = rf"""
    geth:
      ethereum:
        local:
          uri: {GETH_URI}

    test:
      disconnect_providers_after: false
      gas:
        exclude:
          - method_name: fooAndBar
          - method_name: myNumber
          - contract_name: TokenB
    """
    with switch_config(project, config_content):
        result = pytester.runpytest("--gas")
        run_gas_test(result, expected_test_passes, expected_report=expected)


@geth_process_test
@skip_projects_except("geth")
def test_gas_flag_excluding_contracts(geth_provider, setup_pytester, project, pytester):
    expected_test_passes = setup_pytester(project.path.name)
    result = pytester.runpytest("--gas", "--gas-exclude", "TestContractVy,TokenA")
    run_gas_test(result, expected_test_passes, expected_report=TOKEN_B_GAS_REPORT)
