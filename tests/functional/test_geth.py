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
from tests.functional.conftest import RAW_VYPER_CONTRACT_TYPE
from tests.functional.data.python import TRACE_RESPONSE

TRANSACTION_HASH = "0x053cba5c12172654d894f66d5670bab6215517a94189a9ffc09bc40a589ec04d"


@pytest.fixture(scope="module", autouse=True)
def geth(networks):
    with networks.ethereum.local.use_provider("geth") as provider:
        yield provider


@pytest.fixture
def mock_geth(geth, mock_web3):
    provider = Geth(
        name="geth",
        network=geth.network,
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


def test_did_start_local_process(geth):
    assert geth._process is not None
    assert geth._process.is_running


def test_uri(geth):
    assert geth.uri == "http://localhost:8545"


def test_uri_uses_value_from_config(geth, temp_config):
    config = {"geth": {"ethereum": {"local": {"uri": "value/from/config"}}}}
    with temp_config(config):
        assert geth.uri == "value/from/config"


def test_uri_uses_value_from_settings(geth, temp_config):
    # The value from the adhoc-settings is valued over the value from the config file.
    config = {"geth": {"ethereum": {"local": {"uri": "value/from/config"}}}}
    with temp_config(config):
        geth.provider_settings["uri"] = "value/from/settings"
        assert geth.uri == "value/from/settings"
        del geth.provider_settings["uri"]


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


def test_get_call_tree(geth, geth_contract, accounts):
    owner = accounts.test_accounts[-3]
    contract = owner.deploy(geth_contract)
    receipt = contract.setNumber(10, sender=owner)
    result = geth.get_call_tree(receipt.txn_hash)
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


def test_repr_connected(geth):
    assert repr(geth) == "<geth chain_id=1337>"


def test_repr_on_local_network_and_disconnected(networks):
    geth = networks.get_provider_from_choice("ethereum:local:geth")
    assert repr(geth) == "<geth>"


def test_repr_on_live_network_and_disconnected(networks):
    geth = networks.get_provider_from_choice("ethereum:goerli:geth")
    assert repr(geth) == "<geth chain_id=5>"


def test_get_logs(geth, accounts, geth_contract):
    owner = accounts.test_accounts[-4]
    contract = owner.deploy(geth_contract)
    contract.setNumber(101010, sender=owner)
    actual = contract.NumberChange[-1]
    assert actual.event_name == "NumberChange"
    assert actual.contract_address == contract.address
    assert actual.event_arguments["newNum"] == 101010


def test_chain_id_when_connected(geth):
    assert geth.chain_id == 1337


def test_chain_id_live_network_not_connected(networks):
    geth = networks.get_provider_from_choice("ethereum:goerli:geth")
    assert geth.chain_id == 5


def test_chain_id_live_network_connected_uses_web3_chain_id(mocker, geth):
    mock_network = mocker.MagicMock()
    mock_network.chain_id = 999999999  # Shouldn't use hardcoded network
    orig_network = geth.network

    try:
        geth.network = mock_network

        # Still use the connected chain ID instead network's
        assert geth.chain_id == 1337
    finally:
        geth.network = orig_network


def test_connect_wrong_chain_id(mocker, ethereum, geth):
    start_network = geth.network

    try:
        geth.network = ethereum.get_network("goerli")

        # Ensure when reconnecting, it does not use HTTP
        factory = mocker.patch("ape_geth.provider._create_web3")
        factory.return_value = geth._web3
        expected_error_message = (
            "Provider connected to chain ID '1337', "
            "which does not match network chain ID '5'. "
            "Are you connected to 'goerli'?"
        )

        with pytest.raises(NetworkMismatchError, match=expected_error_message):
            geth.connect()
    finally:
        geth.network = start_network


def test_supports_tracing(geth):
    assert geth.supports_tracing


@pytest.mark.parametrize("block_id", (0, "0", "0x0", HexStr("0x0")))
def test_get_block(geth, block_id):
    block = cast(Block, geth.get_block(block_id))

    # Each parameter is the same as requesting the first block.
    assert block.number == 0
    assert block.base_fee == 1000000000
    assert block.gas_used == 0


def test_get_block_not_found(geth):
    latest_block = geth.get_block("latest")
    block_id = latest_block.number + 1000
    with pytest.raises(BlockNotFoundError, match=f"Block with ID '{block_id}' not found."):
        geth.get_block(block_id)


def test_get_receipt_not_exists_with_timeout(geth):
    unknown_txn = TRANSACTION_HASH
    with pytest.raises(TransactionNotFoundError, match=f"Transaction '{unknown_txn}' not found"):
        geth.get_receipt(unknown_txn, timeout=0)


def test_get_receipt(accounts, geth_contract, geth):
    owner = accounts.test_accounts[-5]
    contract = owner.deploy(geth_contract)
    receipt = contract.setNumber(111111, sender=owner)
    actual = geth.get_receipt(receipt.txn_hash)
    assert receipt.txn_hash == actual.txn_hash
    assert actual.receiver == contract.address
    assert actual.sender == receipt.sender
