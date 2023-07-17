import re
import tempfile
from pathlib import Path
from typing import List, cast

import pytest
from eth_typing import HexStr

from ape.exceptions import (
    BlockNotFoundError,
    ContractLogicError,
    NetworkMismatchError,
    OutOfGasError,
    TransactionNotFoundError,
)
from ape_ethereum.ecosystem import Block
from ape_geth.provider import Geth
from tests.conftest import GETH_URI, geth_process_test
from tests.functional.data.python import TRACE_RESPONSE

TRANSACTION_HASH = "0x053cba5c12172654d894f66d5670bab6215517a94189a9ffc09bc40a589ec04d"
LOCAL_TRACE = r"""
Call trace for '0x([A-Fa-f0-9]{64})'
tx\.origin=0x[a-fA-F0-9]{40}
ContractA\.methodWithoutArguments\(\) -> 0x00..5174 \[\d+ gas\]
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
│     \] \[47236 gas\]
├── SYMBOL\.methodB1\(lolol="ice-cream", dynamo=345457847457457458457457457\) \[166680 gas\]
│   ├── ContractC\.getSomeList\(\) -> \[
│   │     3425311345134513461345134534531452345,
│   │     111344445534535353,
│   │     993453434534534534534977788884443333
│   │   \] \[731 gas\]
│   └── ContractC\.methodC1\(
│         windows95="simpler",
│         jamaica=345457847457457458457457457,
│         cardinal=ContractA
│       \) \[114325 gas\]
├── SYMBOL\.callMe\(blue=tx\.origin\) -> tx\.origin \[388 gas\]
├── SYMBOL\.methodB2\(trombone=tx\.origin\) \[127652 gas\]
│   ├── ContractC\.paperwork\(ContractA\) -> \(
│   │     os="simpler",
│   │     country=345457847457457458457457457,
│   │     wings=ContractA
│   │   \) \[1763 gas\]
│   ├── ContractC\.methodC1\(windows95="simpler", jamaica=0, cardinal=ContractC\) \[72525 gas\]
│   ├── ContractC\.methodC2\(\) \[24928 gas\]
│   └── ContractC\.methodC2\(\) \[22928 gas\]
├── ContractC\.addressToValue\(tx.origin\) -> 0 \[2522 gas\]
├── SYMBOL\.bandPractice\(tx.origin\) -> 0 \[558 gas\]
├── SYMBOL\.methodB1\(lolol="lemondrop", dynamo=0\) \[28680 gas\]
│   ├── ContractC\.getSomeList\(\) -> \[
│   │     3425311345134513461345134534531452345,
│   │     111344445534535353,
│   │     993453434534534534534977788884443333
│   │   \] \[731 gas\]
│   └── ContractC\.methodC1\(windows95="simpler", jamaica=0, cardinal=ContractA\) \[24625 gas\]
└── SYMBOL\.methodB1\(lolol="snitches_get_stiches", dynamo=111\) \[48580 gas\]
    ├── ContractC\.getSomeList\(\) -> \[
    │     3425311345134513461345134534531452345,
    │     111344445534535353,
    │     993453434534534534534977788884443333
    │   \] \[731 gas\]
    └── ContractC\.methodC1\(windows95="simpler", jamaica=111, cardinal=ContractA\) \[44525 gas\]
"""


@pytest.fixture
def geth_account(accounts):
    return accounts.test_accounts[5]


@pytest.fixture
def geth_contract(geth_account, vyper_contract_container, geth_provider):
    return geth_account.deploy(vyper_contract_container, 0)


@pytest.fixture
def mock_geth(geth_provider, mock_web3):
    provider = Geth(
        name="geth",
        network=geth_provider.network,
        provider_settings={},
        data_folder=Path("."),
        request_header="",
    )
    original_web3 = provider._web3
    provider._web3 = mock_web3
    yield provider
    provider._web3 = original_web3


@pytest.fixture
def parity_trace_response():
    return TRACE_RESPONSE


@pytest.fixture
def geth_receipt(contract_with_call_depth_geth, owner, geth_provider):
    return contract_with_call_depth_geth.methodWithoutArguments(sender=owner)


@pytest.fixture
def geth_vyper_receipt(geth_vyper_contract, owner):
    return geth_vyper_contract.setNumber(44, sender=owner)


@geth_process_test
def test_uri(geth_provider):
    assert geth_provider.uri == GETH_URI


@geth_process_test
def test_uri_uses_value_from_config(geth_provider, temp_config):
    settings = geth_provider.provider_settings
    geth_provider.provider_settings = {}
    config = {"geth": {"ethereum": {"local": {"uri": "value/from/config"}}}}
    try:
        with temp_config(config):
            assert geth_provider.uri == "value/from/config"
    finally:
        geth_provider.provider_settings = settings


def test_tx_revert(accounts, sender, geth_vyper_contract, owner):
    # 'sender' is not the owner so it will revert (with a message)
    with pytest.raises(ContractLogicError, match="!authorized") as err:
        geth_vyper_contract.setNumber(5, sender=sender)

    assert err.value.txn is not None


def test_revert_no_message(accounts, geth_vyper_contract, owner):
    # The Contract raises empty revert when setting number to 5.
    expected = "Transaction failed."  # Default message
    with pytest.raises(ContractLogicError, match=expected) as err:
        geth_vyper_contract.setNumber(5, sender=owner)

    assert err.value.txn is not None


@geth_process_test
def test_contract_interaction(owner, geth_vyper_contract):
    geth_vyper_contract.setNumber(102, sender=owner)
    assert geth_vyper_contract.myNumber() == 102


@geth_process_test
def test_get_call_tree(geth_vyper_contract, owner, geth_provider):
    receipt = geth_vyper_contract.setNumber(10, sender=owner)
    result = geth_provider.get_call_tree(receipt.txn_hash)
    expected = (
        rf"{geth_vyper_contract.address}.0x3fb5c1cb"
        r"\(0x000000000000000000000000000000000000000000000000000000000000000a\) \[\d+ gas\]"
    )
    actual = repr(result)
    assert re.match(expected, actual)


@geth_process_test
def test_get_call_tree_deploy(geth_vyper_contract, geth_provider):
    receipt = geth_vyper_contract.receipt
    result = geth_provider.get_call_tree(receipt.txn_hash)
    result.enrich()
    expected = rf"{geth_vyper_contract.contract_type.name}\.__new__\(\s*num=\d+\s*\) \[\d+ gas\]"
    actual = repr(result)
    assert re.match(expected, actual)


def test_get_call_tree_erigon(mock_web3, mock_geth, parity_trace_response):
    mock_web3.client_version = "erigon_MOCK"
    mock_web3.provider.make_request.return_value = parity_trace_response
    result = mock_geth.get_call_tree(TRANSACTION_HASH)
    actual = repr(result)
    expected = r"0xC17f2C69aE2E66FD87367E3260412EEfF637F70E.0x96d373e5\(\) \[\d+ gas\]"
    assert re.match(expected, actual)


@geth_process_test
def test_repr_connected(geth_provider):
    assert repr(geth_provider) == "<geth chain_id=1337>"


def test_repr_on_local_network_and_disconnected(networks):
    geth = networks.get_provider_from_choice("ethereum:local:geth")
    assert repr(geth) == "<geth>"


def test_repr_on_live_network_and_disconnected(networks):
    geth = networks.get_provider_from_choice("ethereum:goerli:geth")
    assert repr(geth) == "<geth chain_id=5>"


@geth_process_test
def test_get_logs(geth_vyper_contract, owner):
    geth_vyper_contract.setNumber(101010, sender=owner)
    actual = geth_vyper_contract.NumberChange[-1]
    assert actual.event_name == "NumberChange"
    assert actual.contract_address == geth_vyper_contract.address
    assert actual.event_arguments["newNum"] == 101010


@geth_process_test
def test_chain_id_when_connected(geth_provider):
    assert geth_provider.chain_id == 1337


def test_chain_id_live_network_not_connected(networks):
    geth = networks.get_provider_from_choice("ethereum:goerli:geth")
    assert geth.chain_id == 5


@geth_process_test
def test_chain_id_live_network_connected_uses_web3_chain_id(mocker, geth_provider):
    mock_network = mocker.MagicMock()
    mock_network.chain_id = 999999999  # Shouldn't use hardcoded network
    orig_network = geth_provider.network

    try:
        geth_provider.network = mock_network

        # Still use the connected chain ID instead network's
        assert geth_provider.chain_id == 1337
    finally:
        geth_provider.network = orig_network


@geth_process_test
def test_connect_wrong_chain_id(mocker, ethereum, geth_provider):
    start_network = geth_provider.network

    try:
        geth_provider.network = ethereum.get_network("goerli")

        # Ensure when reconnecting, it does not use HTTP
        factory = mocker.patch("ape_geth.provider._create_web3")
        factory.return_value = geth_provider._web3
        expected_error_message = (
            f"Provider connected to chain ID '{geth_provider._web3.eth.chain_id}', "
            "which does not match network chain ID '5'. "
            "Are you connected to 'goerli'?"
        )

        with pytest.raises(NetworkMismatchError, match=expected_error_message):
            geth_provider.connect()
    finally:
        geth_provider.network = start_network


@geth_process_test
def test_supports_tracing(geth_provider):
    assert geth_provider.supports_tracing


@geth_process_test
@pytest.mark.parametrize("block_id", (0, "0", "0x0", HexStr("0x0")))
def test_get_block(geth_provider, block_id):
    block = cast(Block, geth_provider.get_block(block_id))

    # Each parameter is the same as requesting the first block.
    assert block.number == 0
    assert block.base_fee == 1000000000
    assert block.gas_used == 0


@geth_process_test
def test_get_block_not_found(geth_provider):
    latest_block = geth_provider.get_block("latest")
    block_id = latest_block.number + 1000
    with pytest.raises(BlockNotFoundError, match=f"Block with ID '{block_id}' not found."):
        geth_provider.get_block(block_id)


@geth_process_test
def test_get_receipt_not_exists_with_timeout(geth_provider):
    unknown_txn = TRANSACTION_HASH
    with pytest.raises(TransactionNotFoundError, match=f"Transaction '{unknown_txn}' not found"):
        geth_provider.get_receipt(unknown_txn, timeout=0)


@geth_process_test
def test_get_receipt(accounts, vyper_contract_container, geth_provider):
    owner = accounts.test_accounts[-5]
    contract = owner.deploy(vyper_contract_container, 0)
    receipt = contract.setNumber(111111, sender=owner)
    actual = geth_provider.get_receipt(receipt.txn_hash)
    assert receipt.txn_hash == actual.txn_hash
    assert actual.receiver == contract.address
    assert actual.sender == receipt.sender


@geth_process_test
def test_snapshot_and_revert(geth_provider, geth_account, geth_contract):
    snapshot = geth_provider.snapshot()
    start_nonce = geth_account.nonce
    geth_contract.setNumber(211112, sender=geth_account)  # Advance a block
    actual_block_number = geth_provider.get_block("latest").number
    expected_block_number = snapshot + 1
    actual_nonce = geth_account.nonce
    expected_nonce = start_nonce + 1
    assert actual_block_number == expected_block_number
    assert actual_nonce == expected_nonce

    geth_provider.revert(snapshot)

    actual_block_number = geth_provider.get_block("latest").number
    expected_block_number = snapshot
    actual_nonce = geth_account.nonce
    expected_nonce = start_nonce
    assert actual_block_number == expected_block_number
    assert actual_nonce == expected_nonce

    # Use account after revert
    receipt = geth_contract.setNumber(311113, sender=geth_account)  # Advance a block
    assert not receipt.failed


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


def test_local_transaction_traces(geth_receipt, captrace):
    # NOTE: Strange bug in Rich where we can't use sys.stdout for testing tree output.
    # And we have to write to a file, close it, and then re-open it to see output.
    def run_test():
        with tempfile.TemporaryDirectory() as temp_dir:
            # Use a tempfile to avoid terminal inconsistencies affecting output.
            file_path = Path(temp_dir) / "temp"
            with open(file_path, "w") as file:
                geth_receipt.show_trace(file=file)

            with open(file_path, "r") as file:
                lines = captrace.read_trace("Call trace for", file=file)
                assert_rich_output(lines, LOCAL_TRACE)

    run_test()

    # Verify can happen more than once.
    run_test()


@geth_process_test
def test_contract_logic_error_dev_message(vyper_math_dev_check, owner, geth_provider):
    contract = vyper_math_dev_check.deploy(sender=owner)
    expected = "dev: Integer overflow"
    with pytest.raises(ContractLogicError, match=expected) as err:
        contract.num_add(1, sender=owner)

    assert err.value.txn is not None
    assert err.value.dev_message == expected


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
def test_custom_error(error_contract_geth, not_owner):
    contract = error_contract_geth
    with pytest.raises(contract.Unauthorized) as err:
        contract.withdraw(sender=not_owner)

    assert err.value.txn is not None
    assert err.value.inputs == {"addr": not_owner.address, "counter": 123}


@geth_process_test
def test_custom_error_on_deploy(error_contract_container, owner, chain):
    with pytest.raises(Exception) as err:
        owner.deploy(error_contract_container, 0)

    assert isinstance(err.value, ContractLogicError)
    if err.value.address:
        contract = chain.contracts.instance_at(err.value.address)

        # Ensure it is the custom error.
        assert isinstance(err.value, contract.OtherError)

    else:
        # skip this test - still covered in reverts() tests anyway.
        return


@geth_process_test
def test_return_value_list(geth_account, geth_contract, geth_provider):
    receipt = geth_contract.getFilledArray.transact(sender=geth_account)
    assert receipt.return_value == [1, 2, 3]


@geth_process_test
def test_return_value_nested_address_array(
    geth_account, geth_contract, geth_provider, zero_address
):
    receipt = geth_contract.getNestedAddressArray.transact(sender=geth_account)
    expected = [
        [geth_account.address, geth_account.address, geth_account.address],
        [zero_address, zero_address, zero_address],
    ]
    assert receipt.return_value == expected


@geth_process_test
def test_return_value_nested_struct_in_tuple(geth_account, geth_contract, geth_provider):
    receipt = geth_contract.getNestedStructWithTuple1.transact(sender=geth_account)
    actual = receipt.return_value
    assert actual[0].t.a == geth_account.address
    assert actual[0].foo == 1
    assert actual[1] == 1


@geth_process_test
def test_get_pending_block(geth_provider, geth_account, accounts):
    """
    Pending timestamps can be weird.
    This ensures we can check those are various strange states of geth.
    """
    actual = geth_provider.get_block("latest")
    assert isinstance(actual, Block)

    snap = geth_provider.snapshot()

    # Transact to increase block
    geth_account.transfer(accounts.test_accounts[0], "1 gwei")
    actual = geth_provider.get_block("latest")
    assert isinstance(actual, Block)

    # Restore state before transaction
    geth_provider.revert(snap)
    actual = geth_provider.get_block("latest")
    assert isinstance(actual, Block)


@geth_process_test
def test_isolate(chain, geth_contract, geth_account):
    number_at_start = 444
    geth_contract.setNumber(number_at_start, sender=geth_account)
    start_head = chain.blocks.height

    with chain.isolate():
        geth_contract.setNumber(333, sender=geth_account)
        assert geth_contract.myNumber() == 333
        assert chain.blocks.height == start_head + 1

    assert geth_contract.myNumber() == number_at_start

    # Allow extra 1 to account for potential parallelism-related discrepancy
    assert chain.blocks.height in (start_head, start_head + 1)


@geth_process_test
def test_out_of_gas_error(geth_contract, geth_account, geth_provider):
    """
    Attempt to transact with not quite enough gas. We should get an error saying
    we ran out of gas.
    """
    txn = geth_contract.setNumber.as_transaction(333, sender=geth_account)
    gas = geth_provider.estimate_gas_cost(txn)
    txn.gas_limit = gas - 1
    with pytest.raises(OutOfGasError) as err:
        geth_account.call(txn)

    assert err.value.txn is not None


@geth_process_test
def test_gas_price(geth_provider):
    actual = geth_provider.gas_price
    assert isinstance(actual, int)
