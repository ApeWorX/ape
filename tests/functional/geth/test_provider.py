from typing import cast

import pytest
from eth_typing import HexStr

from ape.exceptions import BlockNotFoundError, NetworkMismatchError, TransactionNotFoundError
from ape_ethereum.ecosystem import Block
from tests.conftest import GETH_URI, geth_process_test


@geth_process_test
def test_uri(geth_provider):
    assert geth_provider.http_uri == GETH_URI
    assert not geth_provider.ws_uri
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


@geth_process_test
def test_repr_connected(geth_provider):
    assert repr(geth_provider) == "<geth chain_id=1337>"


@geth_process_test
def test_repr_on_local_network_and_disconnected(networks):
    geth = networks.get_provider_from_choice("ethereum:local:geth")
    assert repr(geth) == "<geth chain_id=1337>"


@geth_process_test
def test_repr_on_live_network_and_disconnected(networks):
    geth = networks.get_provider_from_choice("ethereum:goerli:geth")
    assert repr(geth) == "<geth chain_id=5>"


@geth_process_test
def test_get_logs(geth_contract, geth_account):
    geth_contract.setNumber(101010, sender=geth_account)
    actual = geth_contract.NumberChange[-1]
    assert actual.event_name == "NumberChange"
    assert actual.contract_address == geth_contract.address
    assert actual.event_arguments["newNum"] == 101010


@geth_process_test
def test_chain_id_when_connected(geth_provider):
    assert geth_provider.chain_id == 1337


@geth_process_test
def test_chain_id_live_network_not_connected(networks):
    geth = networks.get_provider_from_choice("ethereum:goerli:geth")
    assert geth.chain_id == 5


@geth_process_test
def test_chain_id_live_network_connected_uses_web3_chain_id(mocker, geth_provider):
    mock_network = mocker.MagicMock()
    mock_network.chain_id = 999999999  # Shouldn't use hardcoded network
    mock_network.name = "mock"
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
def test_get_receipt_not_exists_with_timeout(geth_provider, txn_hash):
    expected = (
        f"Transaction '{txn_hash}' not found. "
        rf"Error: Transaction HexBytes\('{txn_hash}'\) "
        "is not in the chain after 0 seconds"
    )
    with pytest.raises(TransactionNotFoundError, match=expected):
        geth_provider.get_receipt(txn_hash, timeout=0)


@geth_process_test
def test_get_receipt(accounts, geth_provider, geth_account, geth_contract):
    receipt = geth_contract.setNumber(111111, sender=geth_account)
    actual = geth_provider.get_receipt(receipt.txn_hash)
    assert receipt.txn_hash == actual.txn_hash
    assert actual.receiver == geth_contract.address
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
def test_get_pending_block(geth_provider, geth_account, geth_second_account, accounts):
    """
    Pending timestamps can be weird.
    This ensures we can check those are various strange states of geth.
    """
    actual = geth_provider.get_block("latest")
    assert isinstance(actual, Block)

    snap = geth_provider.snapshot()

    # Transact to increase block
    geth_account.transfer(geth_second_account, "1 gwei")
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
def test_gas_price(geth_provider):
    actual = geth_provider.gas_price
    assert isinstance(actual, int)
