import pytest
from ethpm_types.abi import EventABI

from ape.exceptions import ProviderNotConnectedError
from ape.types import LogFilter, TopicFilter

EXPECTED_CHAIN_ID = 61
RAW_EVENT_ABI = """
{
  "anonymous": false,
  "inputs": [
    {
      "indexed": true,
      "name": "oldVersion",
      "type": "address"
    },
    {
      "indexed": true,
      "name": "newVersion",
      "type": "address"
    }
  ],
  "name": "StrategyMigrated",
  "type": "event"
}
"""


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
    log_filter = LogFilter(contract_addresses=[contract_instance], stop_block=100)
    logs_at_start = len([log for log in eth_tester_provider.get_contract_logs(log_filter)])
    contract_instance.fooAndBar(sender=owner)  # Create 2 logs
    logs_after_new_emit = [log for log in eth_tester_provider.get_contract_logs(log_filter)]
    assert len(logs_after_new_emit) == logs_at_start + 2


def test_get_contract_logs_single_log(contract_instance, owner, eth_tester_provider):
    topic_filter = TopicFilter(event=contract_instance.FooHappened, search_values={"foo": 0})
    log_filter = LogFilter(contract_addresses=[contract_instance], topic_filters=[topic_filter])
    contract_instance.fooAndBar(sender=owner)  # Create logs
    logs = [log for log in eth_tester_provider.get_contract_logs(log_filter)]
    assert len(logs) == 1
    assert logs[0]["foo"] == 0


def test_get_contract_logs_single_log_query_multiple_values(
    contract_instance, owner, eth_tester_provider
):
    topic_filter = TopicFilter(event=contract_instance.FooHappened, search_values={"foo": [0, 1]})
    log_filter = LogFilter(contract_addresses=[contract_instance], topic_filters=[topic_filter])
    contract_instance.fooAndBar(sender=owner)  # Create logs
    logs = [log for log in eth_tester_provider.get_contract_logs(log_filter)]
    assert len(logs) == 1
    assert logs[0]["foo"] == 0


def test_get_contract_logs_single_log_any_value(contract_instance, owner, eth_tester_provider):
    topic_filter = TopicFilter(event=contract_instance.FooHappened, search_values={"foo": None})
    log_filter = LogFilter(contract_addresses=[contract_instance], topic_filters=[topic_filter])
    contract_instance.fooAndBar(sender=owner)  # Create logs
    logs = [log for log in eth_tester_provider.get_contract_logs(log_filter)]
    assert len(logs) == 1
    assert logs[0]["foo"] == 0


def test_get_contract_logs_single_log_unmatched(contract_instance, owner, eth_tester_provider):
    topic_filter = TopicFilter(event=contract_instance.FooHappened, search_values={"foo": 2})
    log_filter = LogFilter(contract_addresses=[contract_instance], topic_filters=[topic_filter])
    contract_instance.fooAndBar(sender=owner)  # Create logs
    logs = [log for log in eth_tester_provider.get_contract_logs(log_filter)]
    assert len(logs) == 0


def test_get_contract_logs_multiple_event_types(contract_instance, owner, eth_tester_provider):
    foo_topic_filter = TopicFilter(event=contract_instance.FooHappened, search_values={"foo": 0})
    bar_topic_filter = TopicFilter(event=contract_instance.BarHappened, search_values={"bar": 1})
    log_filter = LogFilter(
        contract_addresses=[contract_instance], topic_filters=[foo_topic_filter, bar_topic_filter]
    )
    contract_instance.fooAndBar(sender=owner)  # Create logs
    logs = [log for log in eth_tester_provider.get_contract_logs(log_filter)]
    assert len(logs) == 2
    assert logs[0].foo == 0
    assert logs[1].bar == 1


def test_get_contract_logs_multiple_event_types_match_any_value(
    contract_instance, owner, eth_tester_provider
):
    foo_topic_filter = TopicFilter(event=contract_instance.FooHappened, search_values={"foo": None})
    bar_topic_filter = TopicFilter(event=contract_instance.BarHappened, search_values={"bar": None})
    log_filter = LogFilter(
        contract_addresses=[contract_instance],
        topic_filters=[foo_topic_filter, bar_topic_filter],
        stop_block=100,
    )
    contract_instance.fooAndBar(sender=owner)  # Create logs
    logs = [log for log in eth_tester_provider.get_contract_logs(log_filter)]
    assert len(logs) == 2
    assert logs[0].foo == 0
    assert logs[1].bar == 1


def test_topic_filter_encoding():
    event_abi = EventABI.parse_raw(RAW_EVENT_ABI)
    topic_filter = TopicFilter(
        event=event_abi, search_values={"newVersion": "0x8c44Cc5c0f5CD2f7f17B9Aca85d456df25a61Ae8"}
    )
    assert topic_filter.encode() == [
        "0x100b69bb6b504e1252e36b375233158edee64d071b399e2f81473a695fd1b021",
        None,
        "0x0000000000000000000000008c44cc5c0f5cd2f7f17b9aca85d456df25a61ae8",
    ]
