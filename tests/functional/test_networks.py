import pytest
from eth_typing import HexStr

from ape import networks


@pytest.mark.parametrize("block_id", ("latest", 0, "0", "0x0", HexStr("0x0")))
def test_get_block(eth_tester_provider, block_id):
    latest_block = eth_tester_provider.get_block(block_id)

    # Each parameter is the same as requesting the first block.
    assert latest_block.number == 0
    assert latest_block.gas_data.base_fee == 1000000000
    assert latest_block.gas_data.gas_used == 0


def test_get_network_choices_filter_ecosystem():
    actual = {c for c in networks.get_network_choices(ecosystem_filter="ethereum")}
    expected = {c for c in networks.get_network_choices()}
    assert len(actual) == 27
    assert actual == expected


def test_get_network_choices_filter_network():
    actual = {c for c in networks.get_network_choices(network_filter="mainnet-fork")}
    assert actual == set()


def test_get_network_choices_filter_provider():
    actual = {c for c in networks.get_network_choices(provider_filter="test")}
    expected = {"::test", ":local", "ethereum:local", "ethereum:local:test", "ethereum"}
    assert actual == expected
