from unittest import mock

import pytest
from eth_typing import HexStr

from ape.exceptions import BlockNotFoundError, ProviderNotConnectedError, TransactionNotFoundError
from ape.types import LogFilter
from ape_test.provider import CHAIN_ID


@pytest.mark.parametrize("block_id", (0, "0", "0x0", HexStr("0x0")))
def test_get_block(eth_tester_provider, block_id, vyper_contract_instance, owner):
    block = eth_tester_provider.get_block(block_id)

    # Each parameter is the same as requesting the first block.
    assert block.number == 0
    assert block.base_fee == 1000000000
    assert block.gas_used == 0


def test_get_block_not_found(eth_tester_provider):
    latest_block = eth_tester_provider.get_block("latest")
    block_id = latest_block.number + 1000
    with pytest.raises(BlockNotFoundError, match=f"Block with ID '{block_id}' not found."):
        eth_tester_provider.get_block(block_id)


def test_get_block_transaction(vyper_contract_instance, owner, eth_tester_provider):
    # Ensure a transaction in latest block
    receipt = vyper_contract_instance.setNumber(900, sender=owner)
    block = eth_tester_provider.get_block(receipt.block_number)
    assert block.transactions[-1].txn_hash.hex() == receipt.txn_hash


def test_estimate_gas_with_max_value_from_block(mocker, eth_tester_provider):
    mock_txn = mocker.patch("ape.api.networks.NetworkAPI.gas_limit", new_callable=mock.PropertyMock)
    mock_txn.return_value = "max"
    gas_cost = eth_tester_provider.estimate_gas_cost(mock_txn)
    latest_block = eth_tester_provider.get_block("latest")

    assert gas_cost == latest_block.gas_limit


def test_chain_id(eth_tester_provider):
    chain_id = eth_tester_provider.chain_id
    assert chain_id == CHAIN_ID


def test_chain_id_is_cached(eth_tester_provider):
    _ = eth_tester_provider.chain_id

    # Unset `_web3` to show that it is not used in a second call to `chain_id`.
    web3 = eth_tester_provider._web3
    eth_tester_provider._web3 = None
    chain_id = eth_tester_provider.chain_id
    assert chain_id == CHAIN_ID
    eth_tester_provider._web3 = web3  # Undo


def test_chain_id_when_none_raises(eth_tester_provider):
    eth_tester_provider.disconnect()

    with pytest.raises(ProviderNotConnectedError, match="Not connected to a network provider."):
        _ = eth_tester_provider.chain_id

    eth_tester_provider.connect()  # Undo


def test_get_receipt_not_exists_with_timeout(eth_tester_provider):
    unknown_txn = "0x053cba5c12172654d894f66d5670bab6215517a94189a9ffc09bc40a589ec04d"
    with pytest.raises(TransactionNotFoundError, match=f"Transaction '{unknown_txn}' not found"):
        eth_tester_provider.get_receipt(unknown_txn, timeout=0)


def test_get_receipt_exists_with_timeout(eth_tester_provider, vyper_contract_instance, owner):
    receipt_from_invoke = vyper_contract_instance.setNumber(888, sender=owner)
    receipt_from_provider = eth_tester_provider.get_receipt(receipt_from_invoke.txn_hash, timeout=0)
    assert receipt_from_provider.txn_hash == receipt_from_invoke.txn_hash
    assert receipt_from_provider.receiver == vyper_contract_instance.address


def test_get_contracts_logs_all_logs(chain, contract_instance, owner, eth_tester_provider):
    start_block = chain.blocks.height
    stop_block = start_block + 100
    log_filter = LogFilter(
        addresses=[contract_instance],
        events=contract_instance.contract_type.events,
        start_block=start_block,
        stop_block=stop_block,
    )
    logs_at_start = len([log for log in eth_tester_provider.get_contract_logs(log_filter)])
    contract_instance.fooAndBar(sender=owner)  # Create 2 logs
    logs_after_new_emit = [log for log in eth_tester_provider.get_contract_logs(log_filter)]
    assert len(logs_after_new_emit) == logs_at_start + 2


def test_get_contract_logs_single_log(chain, contract_instance, owner, eth_tester_provider):
    contract_instance.fooAndBar(sender=owner)  # Create logs
    block = chain.blocks.height
    log_filter = LogFilter.from_event(
        event=contract_instance.FooHappened,
        search_topics={"foo": 0},
        addresses=[contract_instance],
        start_block=block,
        stop_block=block,
    )
    logs = [log for log in eth_tester_provider.get_contract_logs(log_filter)]
    assert len(logs) == 1
    assert logs[0]["foo"] == 0


def test_get_contract_logs_single_log_query_multiple_values(
    chain, contract_instance, owner, eth_tester_provider
):
    contract_instance.fooAndBar(sender=owner)  # Create logs
    block = chain.blocks.height
    log_filter = LogFilter.from_event(
        event=contract_instance.FooHappened,
        search_topics={"foo": [0, 1]},
        addresses=[contract_instance],
        start_block=block,
        stop_block=block,
    )
    logs = [log for log in eth_tester_provider.get_contract_logs(log_filter)]
    assert len(logs) >= 1
    assert logs[-1]["foo"] == 0


def test_get_contract_logs_single_log_unmatched(
    chain, contract_instance, owner, eth_tester_provider
):
    unmatched_search = {"foo": 2}  # Foo is created with a value of 0
    contract_instance.fooAndBar(sender=owner)  # Create logs
    block = chain.blocks.height
    log_filter = LogFilter.from_event(
        event=contract_instance.FooHappened,
        search_topics=unmatched_search,
        addresses=[contract_instance],
        start_block=block,
        stop_block=block,
    )
    logs = [log for log in eth_tester_provider.get_contract_logs(log_filter)]
    assert len(logs) == 0


def test_supports_tracing(eth_tester_provider):
    assert not eth_tester_provider.supports_tracing


def test_provider_get_balance(project, networks, accounts):
    """
    Test that the address is an AddressType.
    """
    balance = networks.provider.get_balance(accounts.test_accounts[0].address)

    assert type(balance) == int
    assert balance == 1000000000000000000000000
