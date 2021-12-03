import pytest
from eth_typing import HexStr


@pytest.mark.parametrize("block_id", ("latest", 0, "0", "0x0", HexStr("0x0")))
def test_get_block(eth_tester_provider, block_id):
    latest_block = eth_tester_provider.get_block(block_id)

    # Each parameter is the same as requesting the first block.
    assert latest_block.number == 0
    assert latest_block.gas_data.base_fee == 1000000000
    assert latest_block.gas_data.gas_used == 0
