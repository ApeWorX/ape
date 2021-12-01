import pytest


@pytest.mark.parametrize("block_id", ("latest", 0, "0", "0x0"))
def test_get_block(eth_tester_provider, block_id):
    latest_block = eth_tester_provider.get_block(block_id)

    # Each parameter is the same as requesting the first block.
    assert latest_block.number == 0
    assert latest_block.base_fee_per_gas == 1000000000
    assert latest_block.difficulty > 0
    assert latest_block.total_difficulty > 0
    assert latest_block.gas_used == 0
    assert latest_block.miner == "0x0000000000000000000000000000000000000000"
    assert (
        latest_block.parent_hash.hex()
        == "0x0000000000000000000000000000000000000000000000000000000000000000"
    )
