import io
import os
import re
from pathlib import Path
from typing import Optional

import pytest

from ape.pytest.fixtures import PytestApeFixtures
from tests.conftest import GETH_URI, geth_process_test
from tests.integration.cli.utils import skip_projects_except

BASE_PROJECTS_PATH = Path(__file__).parent / "projects"
TOKEN_B_GAS_REPORT = r"""
 +TokenB Gas

  Method +Times called +Min. +Max. +Mean +Median
 ─+
  __init__ +\d +\d+ + \d+ + \d+ + \d+
  balanceOf +\d +\d+ + \d+ + \d+ + \d+
  transfer +\d +\d+ + \d+ + \d+ + \d+
"""
EXPECTED_GAS_REPORT = rf"""
 +VyperContract Gas

  Method +Times called +Min. +Max. +Mean +Median
 ─+
  __init__ +\d +\d+ + \d+ + \d+ + \d+
  fooAndBar +\d +\d+ + \d+ + \d+ + \d+
  myNumber +\d +\d+ + \d+ + \d+ + \d+
  setAddress +\d +\d+ + \d+ + \d+ + \d+
  setNumber +\d +\d+ + \d+ + \d+ + \d+

 +TokenA Gas

  Method +Times called +Min. +Max. +Mean +Median
 ─+
  __init__ +\d +\d+ + \d+ + \d+ + \d+
  balanceOf +\d +\d+ + \d+ + \d+ + \d+
  transfer +\d +\d+ + \d+ + \d+ + \d+
{TOKEN_B_GAS_REPORT}
"""
GETH_LOCAL_CONFIG = f"""
node:
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


@pytest.fixture(autouse=True, scope="session")
def path_check():
    # Fix annoying issue where path cwd doesn't exist
    # Something something temp path.
    try:
        os.getcwd()
    except Exception:
        os.chdir(f"{Path(__file__).parent}")


@pytest.fixture(autouse=True)
def load_dependencies(integ_project):
    """Ensure these are loaded before setting up pytester."""
    integ_project.dependencies.install()


@pytest.fixture
def setup_pytester(pytester, owner):
    # Mine to a new block so we are not capturing old transactions
    # in the tests.
    owner.transfer(owner, 0)

    def setup(project):
        project_path = BASE_PROJECTS_PATH / project.path.name
        tests_path = project_path / "tests"

        # Assume all tests should pass
        num_passes = 0
        num_failed = 0
        test_files = {}
        if tests_path.is_dir():
            for file_path in tests_path.iterdir():
                if file_path.name.startswith("test_") and file_path.suffix == ".py":
                    content = file_path.read_text()
                    test_files[file_path.name] = content
                    num_passes += len(
                        [
                            x
                            for x in content.splitlines()
                            if x.startswith("def test_") and not x.startswith("def test_fail_")
                        ]
                    )
                    num_failed += len(
                        [x for x in content.splitlines() if x.startswith("def test_fail_")]
                    )

            pytester.makepyfile(**test_files)

        # Make other files
        def _make_all_files(base: Path, prefix: Optional[Path] = None):
            if not base.is_dir():
                return

            for file in base.iterdir():
                if file.is_dir() and not file.name == "tests":
                    _make_all_files(file, prefix=Path(file.name))
                elif file.is_file():
                    name = (prefix / file.name).as_posix() if prefix else file.name

                    if name == "ape-config.yaml":
                        # Hack in in-memory overrides for testing purposes.
                        text = str(project.config)
                    else:
                        text = file.read_text()

                    src = {name: text.splitlines()}
                    pytester.makefile(file.suffix, **src)

        _make_all_files(project_path)

        # Check for a conftest.py
        conftest = tests_path / "conftest.py"
        if conftest.is_file():
            pytester.makeconftest(conftest.read_text())

        # Returns expected number of passing tests.
        return num_passes, num_failed

    return setup


def run_gas_test(
    result, expected_passed: int, expected_failed: int, expected_report: str = EXPECTED_GAS_REPORT
):
    result.assert_outcomes(passed=expected_passed, failed=expected_failed), "\n".join(
        result.outlines
    )
    gas_header_line_index = None
    for index, line in enumerate(result.outlines):
        if "Gas Profile" in line:
            gas_header_line_index = index

    assert gas_header_line_index is not None, "'Gas Profile' not in output."
    expected = [x for x in expected_report.rstrip().split("\n")[1:]]
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
def test_test(setup_pytester, integ_project, pytester, eth_tester_provider):
    _ = eth_tester_provider  # Ensure using EthTester for this test.
    passed, failed = setup_pytester(integ_project)
    from ape.logging import logger

    logger.set_level("DEBUG")
    result = pytester.runpytest_subprocess()
    try:
        result.assert_outcomes(passed=passed, failed=failed), "\n".join(result.outlines)
    except ValueError:
        pytest.fail(str(result.stderr))


@skip_projects_except("with-contracts")
def test_uncaught_txn_err(setup_pytester, integ_project, pytester, eth_tester_provider):
    _ = eth_tester_provider  # Ensure using EthTester for this test.
    setup_pytester(integ_project)
    result = pytester.runpytest_subprocess()
    expected = """
    contract_in_test.setNumber(5, sender=owner)
E   ape.exceptions.ContractLogicError: Transaction failed.
    """.strip()
    assert expected in str(result.stdout)


@skip_projects_except("with-contracts")
def test_show_internal(setup_pytester, integ_project, pytester, eth_tester_provider):
    _ = eth_tester_provider  # Ensure using EthTester for this test.
    setup_pytester(integ_project)
    result = pytester.runpytest_subprocess("--show-internal")
    expected = """
    raise vm_err from err
E   ape.exceptions.ContractLogicError: Transaction failed.
    """.strip()
    assert expected in str(result.stdout)


@skip_projects_except("test", "with-contracts")
def test_test_isolation_disabled(setup_pytester, integ_project, pytester, eth_tester_provider):
    # check the disable isolation option actually disables built-in isolation
    _ = eth_tester_provider  # Ensure using EthTester for this test.
    setup_pytester(integ_project)
    result = pytester.runpytest_subprocess("--disable-isolation", "--setup-show")
    assert "F _function_isolation" not in "\n".join(result.outlines)


@skip_projects_except("test", "with-contracts")
def test_fixture_docs(setup_pytester, integ_project, pytester, eth_tester_provider):
    _ = eth_tester_provider  # Ensure using EthTester for this test.
    result = pytester.runpytest_subprocess("-q", "--fixtures")
    actual = "\n".join(result.outlines)

    # 'accounts', 'networks', 'chain', and 'project' (etc.)
    fixtures = [prop for n, prop in vars(PytestApeFixtures).items() if not n.startswith("_")]
    for fixture in fixtures:
        # The doc str of the fixture shows in the CLI output
        for doc_str in fixture.__doc__.splitlines():
            assert doc_str.strip() in actual


@skip_projects_except("with-contracts")
def test_gas_flag_when_not_supported(setup_pytester, integ_project, pytester, eth_tester_provider):
    _ = eth_tester_provider  # Ensure using EthTester for this test.
    setup_pytester(integ_project)
    path = f"{integ_project.path}/tests/test_contract.py::test_contract_interaction_in_tests"
    result = pytester.runpytest(path, "--gas")
    actual = "\n".join(result.outlines)
    expected = (
        "Provider 'test' does not support transaction tracing. "
        "The gas profile is limited to receipt-level data."
    )
    assert expected in actual


@geth_process_test
@skip_projects_except("geth")
def test_gas_flag_in_tests(geth_provider, setup_pytester, integ_project, pytester, owner):
    owner.transfer(owner, "1 wei")  # Do this to force a clean slate.
    passed, failed = setup_pytester(integ_project)
    result = pytester.runpytest_subprocess("--gas", "--network", "ethereum:local:node")
    run_gas_test(result, passed, failed)


@geth_process_test
@skip_projects_except("geth")
def test_gas_flag_set_in_config(
    geth_provider, setup_pytester, integ_project, pytester, geth_account
):
    geth_account.transfer(geth_account, "1 wei")  # Force a clean block.
    cfg = integ_project.config.model_dump(by_alias=True, mode="json")
    cfg["test"]["gas"] = {"reports": ["terminal"]}
    with integ_project.temp_config(**cfg):
        passed, failed = setup_pytester(integ_project)
        result = pytester.runpytest_subprocess("--network", "ethereum:local:node")
        run_gas_test(result, passed, failed)


@geth_process_test
@skip_projects_except("geth")
def test_gas_when_estimating(geth_provider, setup_pytester, integ_project, pytester, geth_account):
    """
    Shows that gas reports still work when estimating gas.
    """
    cfg = integ_project.config.model_dump(by_alias=True, mode="json")
    cfg["test"]["gas"] = {"reports": ["terminal"]}
    geth_account.transfer(geth_account, "1 wei")  # Force a clean block.
    with integ_project.temp_config(**cfg):
        passed, failed = setup_pytester(integ_project)
        result = pytester.runpytest_subprocess()
        run_gas_test(result, passed, failed)


@geth_process_test
@skip_projects_except("geth")
def test_gas_flag_exclude_using_cli_option(
    geth_provider, setup_pytester, integ_project, pytester, geth_account
):
    geth_account.transfer(geth_account, "1 wei")  # Force a clean block.
    passed, failed = setup_pytester(integ_project)
    # NOTE: Includes both a mutable and a view method.
    expected = filter_expected_methods("fooAndBar", "myNumber")
    # Also ensure can filter out whole class
    expected = expected.replace(TOKEN_B_GAS_REPORT, "")
    result = pytester.runpytest_subprocess(
        "--gas",
        "--gas-exclude",
        "*:fooAndBar,*:myNumber,tokenB:*",
        "--network",
        "ethereum:local:node",
    )
    run_gas_test(result, passed, failed, expected_report=expected)


@geth_process_test
@skip_projects_except("geth")
def test_gas_flag_exclusions_set_in_config(
    geth_provider, setup_pytester, integ_project, pytester, geth_account
):
    geth_account.transfer(geth_account, "1 wei")  # Force a clean block.
    # NOTE: Includes both a mutable and a view method.
    expected = filter_expected_methods("fooAndBar", "myNumber")
    # Also ensure can filter out whole class
    expected = expected.replace(TOKEN_B_GAS_REPORT, "")
    cfg = integ_project.config.model_dump(by_alias=True, mode="json")
    cfg["test"]["gas"] = {
        "exclude": [
            {"method_name": "fooAndBar"},
            {"method_name": "myNumber"},
            {"contract_name": "TokenB"},
        ]
    }
    with integ_project.temp_config(**cfg):
        passed, failed = setup_pytester(integ_project)
        result = pytester.runpytest_subprocess("--gas", "--network", "ethereum:local:node")
        run_gas_test(result, passed, failed, expected_report=expected)


@geth_process_test
@skip_projects_except("geth")
def test_gas_flag_excluding_contracts(
    geth_provider, setup_pytester, integ_project, pytester, geth_account
):
    geth_account.transfer(geth_account, "1 wei")  # Force a clean block.
    passed, failed = setup_pytester(integ_project)
    result = pytester.runpytest_subprocess(
        "--gas", "--gas-exclude", "VyperContract,TokenA", "--network", "ethereum:local:node"
    )
    run_gas_test(result, passed, failed, expected_report=TOKEN_B_GAS_REPORT)


@geth_process_test
@skip_projects_except("geth")
def test_coverage(geth_provider, setup_pytester, integ_project, pytester, geth_account):
    """
    Ensures the --coverage flag works.
    For better coverage tests, see ape-vyper because the Vyper
    plugin is what implements the `trace_source()` method which does the bulk
    of the coverage work.
    """
    geth_account.transfer(geth_account, "1 wei")  # Force a clean block.
    passed, failed = setup_pytester(integ_project)
    result = pytester.runpytest_subprocess(
        "--coverage", "--show-internal", "--network", "ethereum:local:node"
    )
    result.assert_outcomes(passed=passed, failed=failed)


@skip_projects_except("with-contracts")
def test_interactive(eth_tester_provider, integ_project, pytester, monkeypatch):
    secret = "__ 123 super secret 123 __"
    test = f"""
def test_fails():
    foo = "{secret}"
    raise Exception("__FAIL__")
"""
    pytester.makepyfile(test)
    stdin = "print(foo)\nexit\n"
    monkeypatch.setattr("sys.stdin", io.StringIO(stdin))
    result = pytester.runpytest("--interactive", "-s")
    result.assert_outcomes(failed=1)
    actual = str(result.stdout)
    assert secret in actual
    assert "__FAIL__" in actual
