import re

import pytest

from ape.utils import run_in_tempdir
from ape_ethereum.trace import CallTrace, Trace, TraceApproach, TransactionTrace
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
│   \] \[\d+ gas\]
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


def assert_rich_output(rich_capture: list[str], expected: str):
    expected_lines = [x.rstrip() for x in expected.splitlines() if x.rstrip()]
    actual_lines = [x.rstrip() for x in rich_capture if x.rstrip()]
    assert actual_lines, "No output."
    output = "\n".join(actual_lines)

    for actual, expected in zip(actual_lines, expected_lines):
        fail_message = f"""\n
        \tPattern: {expected}\n
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
def test_str_and_repr(geth_contract, geth_account, geth_provider):
    receipt = geth_contract.setNumber(10, sender=geth_account)
    trace = geth_provider.get_transaction_trace(receipt.txn_hash)
    expected = rf"{geth_contract.contract_type.name}\.setNumber\(\s*num=\d+\s*\) \[\d+ gas\]"
    for actual in (str(trace), repr(trace)):
        assert re.match(expected, actual)


@geth_process_test
def test_str_and_repr_deploy(geth_contract, geth_provider):
    creation = geth_contract.creation_metadata
    trace = geth_provider.get_transaction_trace(creation.txn_hash)
    _ = trace.enriched_calltree
    expected = rf"{geth_contract.contract_type.name}\.__new__\(\s*num=\d+\s*\) \[\d+ gas\]"
    for actual in (str(trace), repr(trace)):
        assert re.match(expected, actual), f"Unexpected repr: {actual}"


@geth_process_test
def test_str_and_repr_erigon(
    parity_trace_response, geth_provider, mock_web3, networks, mock_geth, geth_contract
):
    mock_web3.client_version = "erigon_MOCK"

    def _request(rpc, arguments):
        if rpc == "trace_transaction":
            return parity_trace_response

        return geth_provider.web3.provider.make_request(rpc, arguments)

    mock_web3.provider.make_request.side_effect = _request
    mock_web3.eth = geth_provider.web3.eth
    orig_provider = networks.active_provider
    networks.active_provider = mock_geth
    expected = r"0x[a-fA-F0-9]{40}\.0x[a-fA-F0-9]+\(\) \[\d+ gas\]"

    try:
        creation = geth_contract.creation_metadata
        trace = mock_geth.get_transaction_trace(creation.txn_hash)
        assert isinstance(trace, Trace)
        for actual in (str(trace), repr(trace)):
            assert re.match(expected, actual), actual

    finally:
        networks.active_provider = orig_provider


@geth_process_test
def test_str_multiline(geth_contract, geth_account):
    tx = geth_contract.getNestedAddressArray.transact(sender=geth_account)
    actual = f"{tx.trace}"
    expected = r"""
VyperContract\.getNestedAddressArray\(\) -> \[
    \['tx\.origin', 'tx\.origin', 'tx\.origin'\],
    \['ZERO_ADDRESS', 'ZERO_ADDRESS', 'ZERO_ADDRESS'\]
\] \[\d+ gas\]
"""
    assert re.match(expected.strip(), actual.strip())


@geth_process_test
def test_str_list_of_lists(geth_contract, geth_account):
    tx = geth_contract.getNestedArrayMixedDynamic.transact(sender=geth_account)
    actual = f"{tx.trace}"
    expected = r"""
VyperContract\.getNestedArrayMixedDynamic\(\) -> \[
    \[\[\[0\], \[0, 1\], \[0, 1, 2\]\]\],
    \[
        \[\[0\], \[0, 1\], \[0, 1, 2\]\],
        \[\[0\], \[0, 1\], \[0, 1, 2\]\]
    \],
    \[\],
    \[\],
    \[\]
\] \[\d+ gas\]
"""
    assert re.match(expected.strip(), actual.strip())


@geth_process_test
def test_get_gas_report(gas_tracker, geth_account, geth_contract):
    tx = geth_contract.setNumber(924, sender=geth_account)
    trace = tx.trace
    actual = trace.get_gas_report()
    contract_name = geth_contract.contract_type.name
    expected = {contract_name: {"setNumber": [tx.gas_used]}}
    assert actual == expected


@geth_process_test
def test_get_gas_report_deploy(gas_tracker, geth_contract):
    tx = geth_contract.creation_metadata.receipt
    trace = tx.trace
    actual = trace.get_gas_report()
    contract_name = geth_contract.contract_type.name
    expected = {contract_name: {"__new__": [tx.gas_used]}}
    assert actual == expected


@geth_process_test
def test_transaction_trace_create(vyper_contract_instance):
    tx_hash = vyper_contract_instance.creation_metadata.txn_hash
    trace = TransactionTrace(transaction_hash=tx_hash)
    actual = f"{trace}"
    expected = r"VyperContract\.__new__\(num=0\) \[\d+ gas\]"
    assert re.match(expected, actual)


@geth_process_test
def test_get_transaction_trace_erigon_calltree(
    parity_trace_response, geth_provider, mock_web3, mocker
):
    # hash defined in parity_trace_response
    tx_hash = "0x3cef4aaa52b97b6b61aa32b3afcecb0d14f7862ca80fdc76504c37a9374645c4"
    default_make_request = geth_provider.web3.provider.make_request

    def hacked_make_request(rpc, arguments):
        if rpc == "trace_transaction":
            return parity_trace_response

        return default_make_request(rpc, arguments)

    mock_web3.provider.make_request.side_effect = hacked_make_request
    original_web3 = geth_provider._web3
    geth_provider._web3 = mock_web3
    trace = geth_provider.get_transaction_trace(tx_hash, call_trace_approach=TraceApproach.PARITY)
    trace.__dict__["transaction"] = mocker.MagicMock()  # doesn't matter.
    result = trace.enriched_calltree

    # Defined in parity_mock_response
    assert result["contract_id"] == "0xC17f2C69aE2E66FD87367E3260412EEfF637F70E"
    assert result["method_id"] == "0x96d373e5"

    geth_provider._web3 = original_web3


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


@geth_process_test
def test_call_trace_supports_debug_trace_call(geth_contract, geth_account):
    tx = {
        "chainId": "0x539",
        "to": "0x77c7E3905c21177Be97956c6620567596492C497",
        "value": "0x0",
        "data": "0x23fd0e40",
        "type": 2,
        "accessList": [],
    }
    trace = CallTrace(tx=tx)
    _ = trace._traced_call
    assert trace.supports_debug_trace_call
