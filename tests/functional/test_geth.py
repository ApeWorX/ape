import re
from pathlib import Path
from typing import cast

import pytest
from eth_typing import HexStr
from ethpm_types import ContractType

from ape.contracts import ContractContainer
from ape.exceptions import (
    BlockNotFoundError,
    ContractLogicError,
    NetworkMismatchError,
    TransactionNotFoundError,
)
from ape_ethereum.ecosystem import Block
from ape_geth.provider import Geth
from tests.conftest import GETH_URI, geth_process_test
from tests.functional.conftest import RAW_VYPER_CONTRACT_TYPE
from tests.functional.data.python import TRACE_RESPONSE

TRANSACTION_HASH = "0x053cba5c12172654d894f66d5670bab6215517a94189a9ffc09bc40a589ec04d"


@geth_process_test
@pytest.fixture
def mock_geth(geth_provider, mock_web3):
    provider = Geth(
        name="geth",
        network=geth_provider.network,
        provider_settings={},
        data_folder=Path("."),
        request_header="",
    )
    provider._web3 = mock_web3
    return provider


@pytest.fixture(scope="module")
def geth_contract():
    contract_type = ContractType.parse_raw(RAW_VYPER_CONTRACT_TYPE)
    return ContractContainer(contract_type=contract_type)


@pytest.fixture
def parity_trace_response():
    return TRACE_RESPONSE


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


def test_tx_revert(accounts, sender, geth_contract):
    # 'sender' is not the owner so it will revert (with a message)
    contract = accounts.test_accounts[-1].deploy(geth_contract)
    with pytest.raises(ContractLogicError, match="!authorized"):
        contract.setNumber(5, sender=sender)


def test_revert_no_message(accounts, geth_contract):
    # The Contract raises empty revert when setting number to 5.
    expected = "Transaction failed."  # Default message
    owner = accounts.test_accounts[-2]
    contract = owner.deploy(geth_contract)
    with pytest.raises(ContractLogicError, match=expected):
        contract.setNumber(5, sender=owner)


@geth_process_test
def test_contract_interaction(geth_provider, geth_contract, accounts):
    owner = accounts.test_accounts[-2]
    contract = owner.deploy(geth_contract)
    contract.setNumber(102, sender=owner)
    assert contract.myNumber() == 102


@geth_process_test
def test_get_call_tree(geth_provider, geth_contract, accounts):
    owner = accounts.test_accounts[-3]
    contract = owner.deploy(geth_contract)
    receipt = contract.setNumber(10, sender=owner)
    result = geth_provider.get_call_tree(receipt.txn_hash)
    expected = rf"CALL: {contract.address}.<0x3fb5c1cb> \[\d+ gas\]"
    actual = repr(result)
    assert re.match(expected, actual)


def test_get_call_tree_erigon(mock_web3, mock_geth, parity_trace_response):
    mock_web3.client_version = "erigon_MOCK"
    mock_web3.provider.make_request.return_value = parity_trace_response
    result = mock_geth.get_call_tree(TRANSACTION_HASH)
    actual = repr(result)
    expected = r"CALL: 0xC17f2C69aE2E66FD87367E3260412EEfF637F70E.<0x96d373e5> \[\d+ gas\]"
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
def test_get_logs(geth_provider, accounts, geth_contract):
    owner = accounts.test_accounts[-4]
    contract = owner.deploy(geth_contract)
    contract.setNumber(101010, sender=owner)
    actual = contract.NumberChange[-1]
    assert actual.event_name == "NumberChange"
    assert actual.contract_address == contract.address
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
            "Provider connected to chain ID '1337', "
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
def test_get_receipt(accounts, geth_contract, geth_provider):
    owner = accounts.test_accounts[-5]
    contract = owner.deploy(geth_contract)
    receipt = contract.setNumber(111111, sender=owner)
    actual = geth_provider.get_receipt(receipt.txn_hash)
    assert receipt.txn_hash == actual.txn_hash
    assert actual.receiver == contract.address
    assert actual.sender == receipt.sender


@pytest.mark.skip("https://github.com/ethereum/go-ethereum/issues/26154")
@geth_process_test
def test_snapshot_and_revert(geth_provider, accounts, geth_contract):
    owner = accounts.test_accounts[-6]
    contract = owner.deploy(geth_contract)

    snapshot = geth_provider.snapshot()
    start_nonce = owner.nonce
    contract.setNumber(211112, sender=owner)  # Advance a block
    actual_block_number = geth_provider.get_block("latest").number
    expected_block_number = snapshot + 1
    actual_nonce = owner.nonce
    expected_nonce = start_nonce + 1
    assert actual_block_number == expected_block_number
    assert actual_nonce == expected_nonce

    geth_provider.revert(snapshot)

    actual_block_number = geth_provider.get_block("latest").number
    expected_block_number = snapshot
    actual_nonce = owner.nonce
    expected_nonce = start_nonce
    assert actual_block_number == expected_block_number
    assert actual_nonce == expected_nonce

    # Use account after revert
    receipt = contract.setNumber(311113, sender=owner)  # Advance a block
    assert not receipt.failed
