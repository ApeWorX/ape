import pytest

from ape.exceptions import ProviderNotConnectedError

EXPECTED_CHAIN_ID = 61


def test_chain_id(eth_tester_provider):
    chain_id = eth_tester_provider.chain_id
    assert chain_id == EXPECTED_CHAIN_ID


def test_chain_id_is_cached(eth_tester_provider):
    _ = eth_tester_provider.chain_id

    # Unset `_web3` to show that it is not used in a second call to `chain_id`.
    web3 = eth_tester_provider._web3
    eth_tester_provider._web3 = None
    chain_id = eth_tester_provider.chain_id
    assert chain_id == EXPECTED_CHAIN_ID
    eth_tester_provider._web3 = web3  # Undo


def test_chain_id_when_none_raises(eth_tester_provider):
    eth_tester_provider.disconnect()

    with pytest.raises(ProviderNotConnectedError, match="Not connected to a network provider."):
        _ = eth_tester_provider.chain_id

    eth_tester_provider.connect()  # Undo


def test_get_contracts_logs_all_logs(contract_instance, owner, eth_tester_provider):
    logs_at_start = len(
        [log for log in eth_tester_provider.get_contract_logs(contract_instance.address)]
    )
    contract_instance.fooAndBar(sender=owner)  # Create 2 logs
    logs = [log for log in eth_tester_provider.get_contract_logs(contract_instance.address)]
    assert len(logs) == logs_at_start + 2


def test_get_contract_logs_single_log(contract_instance, owner, eth_tester_provider):
    foo_happened = contract_instance.FooHappened
    query = [(foo_happened.abi, {"foo": 0})]
    contract_instance.fooAndBar(sender=owner)  # Create logs
    logs = [
        log for log in eth_tester_provider.get_contract_logs([contract_instance.address], query)
    ]
    assert len(logs) == 1
    assert logs[0]["foo"] == 0


def test_get_contract_logs_single_log_query_multiple_values(
    contract_instance, owner, eth_tester_provider
):
    foo_happened = contract_instance.FooHappened
    query = [(foo_happened.abi, {"foo": [0, 1]})]
    contract_instance.fooAndBar(sender=owner)  # Create logs
    logs = [
        log for log in eth_tester_provider.get_contract_logs([contract_instance.address], query)
    ]
    assert len(logs) == 1
    assert logs[0]["foo"] == 0


def test_get_contract_logs_single_log_any_value(contract_instance, owner, eth_tester_provider):
    # NOTE: ``None`` means it matches everything at the topic position.
    foo_happened = contract_instance.FooHappened
    query = [
        (foo_happened.abi, {"foo": None}),
    ]
    contract_instance.fooAndBar(sender=owner)  # Create logs

    logs = [
        log for log in eth_tester_provider.get_contract_logs([contract_instance.address], query)
    ]

    assert len(logs) == 1
    assert logs[0]["foo"] == 0


def test_get_contract_logs_single_log_unmatched(contract_instance, owner, eth_tester_provider):
    # NOTE: ``None`` means it matches everything at the topic position.
    foo_happened = contract_instance.FooHappened
    query = [
        (foo_happened.abi, {"foo": 2}),
    ]
    contract_instance.fooAndBar(sender=owner)  # Create logs
    logs = [
        log for log in eth_tester_provider.get_contract_logs([contract_instance.address], query)
    ]
    assert len(logs) == 0


def test_get_contract_logs_multiple_event_types(contract_instance, owner, eth_tester_provider):
    foo_happened = contract_instance.FooHappened
    bar_happened = contract_instance.BarHappened
    contract_instance.fooAndBar(sender=owner)  # Create logs

    query = [(foo_happened.abi, {"foo": 0}), (bar_happened.abi, {"bar": 1})]
    logs = [
        log for log in eth_tester_provider.get_contract_logs([contract_instance.address], query)
    ]

    assert len(logs) == 2
    assert logs[0].foo == 0
    assert logs[1].bar == 1


def test_get_contract_logs_multiple_event_types_match_any_value(
    contract_instance, owner, eth_tester_provider
):
    foo_happened = contract_instance.FooHappened
    bar_happened = contract_instance.BarHappened
    contract_instance.fooAndBar(sender=owner)  # Create logs

    query = [(foo_happened.abi, {"foo": None}), (bar_happened.abi, {"bar": None})]
    logs = [
        log for log in eth_tester_provider.get_contract_logs([contract_instance.address], query)
    ]

    assert len(logs) == 2
    assert logs[0].foo == 0
    assert logs[1].bar == 1
