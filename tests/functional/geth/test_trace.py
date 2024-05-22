import re
from typing import List

import pytest

from ape.utils import run_in_tempdir
from tests.conftest import geth_process_test

LOCAL_TRACE = r"""
Call trace for '0x([A-Fa-f0-9]{64})'
tx\.origin=0x[a-fA-F0-9]{40}
ContractA\.methodWithoutArguments\(\) -> 0x[A-Fa-f0-9]{2}..[A-Fa-f0-9]{4} \[\d+ gas\]
├── SYMBOL\.supercluster\(x=234444\) -> \[
│       \[23523523235235, 11111111111, 234444\],
│       \[
│         345345347789999991,
│         99999998888882,
│         345457847457457458457457457
│       \],
│       \[234444, 92222229999998888882, 3454\],
│       \[
│         111145345347789999991,
│         333399998888882,
│         234545457847457457458457457457
│       \]
│     \] \[\d+ gas\]
├── SYMBOL\.methodB1\(lolol="ice-cream", dynamo=345457847457457458457457457\) \[\d+ gas\]
│   ├── ContractC\.getSomeList\(\) -> \[
│   │     3425311345134513461345134534531452345,
│   │     111344445534535353,
│   │     993453434534534534534977788884443333
│   │   \] \[\d+ gas\]
│   └── ContractC\.methodC1\(
│         windows95="simpler",
│         jamaica=345457847457457458457457457,
│         cardinal=ContractA
│       \) \[\d+ gas\]
├── SYMBOL\.callMe\(blue=tx\.origin\) -> tx\.origin \[\d+ gas\]
├── SYMBOL\.methodB2\(trombone=tx\.origin\) \[\d+ gas\]
│   ├── ContractC\.paperwork\(ContractA\) -> \(
│   │     os="simpler",
│   │     country=345457847457457458457457457,
│   │     wings=ContractA
│   │   \) \[\d+ gas\]
│   ├── ContractC\.methodC1\(windows95="simpler", jamaica=0, cardinal=ContractC\) \[\d+ gas\]
│   ├── ContractC\.methodC2\(\) \[\d+ gas\]
│   └── ContractC\.methodC2\(\) \[\d+ gas\]
├── ContractC\.addressToValue\(tx.origin\) -> 0 \[\d+ gas\]
├── SYMBOL\.bandPractice\(tx.origin\) -> 0 \[\d+ gas\]
├── SYMBOL\.methodB1\(lolol="lemondrop", dynamo=0\) \[\d+ gas\]
│   ├── ContractC\.getSomeList\(\) -> \[
│   │     3425311345134513461345134534531452345,
│   │     111344445534535353,
│   │     993453434534534534534977788884443333
│   │   \] \[\d+ gas\]
│   └── ContractC\.methodC1\(windows95="simpler", jamaica=0, cardinal=ContractA\) \[\d+ gas\]
└── SYMBOL\.methodB1\(lolol="snitches_get_stiches", dynamo=111\) \[\d+ gas\]
    ├── ContractC\.getSomeList\(\) -> \[
    │     3425311345134513461345134534531452345,
    │     111344445534535353,
    │     993453434534534534534977788884443333
    │   \] \[\d+ gas\]
    └── ContractC\.methodC1\(windows95="simpler", jamaica=111, cardinal=ContractA\) \[\d+ gas\]
"""


@pytest.fixture
def local_trace():
    return LOCAL_TRACE


@pytest.fixture
def captrace(capsys):
    class CapTrace:
        def read_trace(self, expected_start: str, file=None):
            lines = file.readlines() if file else capsys.readouterr().out.splitlines()
            start_index = 0
            for index, line in enumerate(lines):
                if line.strip().startswith(expected_start):
                    start_index = index
                    break

            return lines[start_index:]

    return CapTrace()


@geth_process_test
def test_supports_tracing(geth_provider):
    assert geth_provider.supports_tracing


@geth_process_test
def test_local_transaction_traces(geth_receipt, captrace, local_trace):
    # NOTE: Strange bug in Rich where we can't use sys.stdout for testing tree output.
    # And we have to write to a file, close it, and then re-open it to see output.
    def run_test(path):
        # Use a tempfile to avoid terminal inconsistencies affecting output.
        with open(path / "temp", "w") as file:
            geth_receipt.show_trace(file=file)

        with open(path / "temp", "r") as file:
            lines = captrace.read_trace("Call trace for", file=file)
            assert_rich_output(lines, local_trace)

    run_in_tempdir(run_test)

    # Verify can happen more than once.
    run_in_tempdir(run_test, name="temp")


def assert_rich_output(rich_capture: List[str], expected: str):
    expected_lines = [x.rstrip() for x in expected.splitlines() if x.rstrip()]
    actual_lines = [x.rstrip() for x in rich_capture if x.rstrip()]
    assert actual_lines, "No output."
    output = "\n".join(actual_lines)

    for actual, expected in zip(actual_lines, expected_lines):
        fail_message = f"""\n
        \tPattern: {expected},\n
        \tLine   : {actual}\n
        \n
        Complete output:
        \n{output}
        """

        try:
            assert re.match(expected, actual), fail_message
        except AssertionError:
            raise  # Let assertion errors raise as normal.
        except Exception as err:
            pytest.fail(f"{fail_message}\n{err}")

    actual_len = len(actual_lines)
    expected_len = len(expected_lines)
    if expected_len > actual_len:
        rest = "\n".join(expected_lines[actual_len:])
        pytest.fail(f"Missing expected lines: {rest}")


@geth_process_test
def test_get_call_tree(geth_contract, geth_account, geth_provider):
    receipt = geth_contract.setNumber(10, sender=geth_account)
    result = geth_provider.get_call_tree(receipt.txn_hash)
    expected = (
        rf"{geth_contract.address}.0x3fb5c1cb"
        r"\(0x000000000000000000000000000000000000000000000000000000000000000a\) \[\d+ gas\]"
    )
    actual = repr(result)
    assert re.match(expected, actual)


@geth_process_test
def test_get_call_tree_deploy(geth_contract, geth_provider):
    receipt = geth_contract.receipt
    result = geth_provider.get_call_tree(receipt.txn_hash)
    result.enrich()
    expected = rf"{geth_contract.contract_type.name}\.__new__\(\s*num=\d+\s*\) \[\d+ gas\]"
    actual = repr(result)
    assert re.match(expected, actual)


@geth_process_test
def test_get_call_tree_erigon(mock_web3, mock_geth, parity_trace_response, txn_hash):
    mock_web3.client_version = "erigon_MOCK"
    mock_web3.provider.make_request.return_value = parity_trace_response
    result = mock_geth.get_call_tree(txn_hash)
    actual = repr(result)
    expected = r"0xC17f2C69aE2E66FD87367E3260412EEfF637F70E.0x96d373e5\(\) \[\d+ gas\]"
    assert re.match(expected, actual)


@geth_process_test
def test_printing_debug_logs_vyper(geth_provider, geth_account, vyper_printing):
    num = 789
    # Why is 6 afraid of 7?  Because {num}
    receipt = vyper_printing.print_uint(num, sender=geth_account)
    assert receipt.status
    assert len(list(receipt.debug_logs_typed)) == 1
    assert receipt.debug_logs_typed[0][0] == num


@geth_process_test
def test_printing_debug_logs_compat(geth_provider, geth_account, vyper_printing):
    num = 456
    receipt = vyper_printing.print_uint_compat(num, sender=geth_account)
    assert receipt.status
    assert len(list(receipt.debug_logs_typed)) == 1
    assert receipt.debug_logs_typed[0][0] == num
