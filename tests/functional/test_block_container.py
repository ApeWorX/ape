import time
from queue import Queue

import pytest
from eth_pydantic_types import HexBytes

from ape.exceptions import ChainError, ProviderError


def test_iterate_blocks(chain_that_mined_5):
    blocks = [b for b in chain_that_mined_5.blocks]
    assert len(blocks) >= 5  # Because mined 5 blocks so is at least 5

    iterator = blocks[0].number
    for block in blocks:
        assert block.number == iterator
        iterator += 1


def test_blocks_range(chain_that_mined_5):
    # The number of the block before mining the 5
    start_block = len(chain_that_mined_5.blocks) - 5
    num_to_get = 3  # Expecting blocks [s, s+1, s+2]
    blocks = [b for b in chain_that_mined_5.blocks.range(start_block, start_block + num_to_get)]
    assert len(blocks) == num_to_get

    expected_number = start_block
    prev_block_hash = (
        HexBytes("0x0000000000000000000000000000000000000000000000000000000000000000")
        if start_block == 0
        else chain_that_mined_5.blocks[start_block - 1].hash
    )
    for block in blocks:
        assert block.number == expected_number
        expected_number += 1
        assert block.parent_hash == prev_block_hash
        prev_block_hash = block.hash


def test_blocks_range_too_high_stop(chain_that_mined_5):
    num_blocks = len(chain_that_mined_5.blocks)
    num_blocks_add_1 = num_blocks + 1
    expected = (
        rf"'stop={num_blocks_add_1}' cannot be greater than the chain length \({num_blocks}\)\. "
        rf"Use 'poll_blocks\(\)' to wait for future blocks\."
    )
    with pytest.raises(ChainError, match=expected):
        # Have to run through generator to trigger code in definition.
        list(chain_that_mined_5.blocks.range(num_blocks_add_1))


def test_block_range_with_step(chain_that_mined_5):
    blocks = [b for b in chain_that_mined_5.blocks.range(3, step=2)]
    assert len(blocks) == 2
    assert blocks[0].number == 0
    assert blocks[1].number == 2


def test_block_range_negative_start(chain_that_mined_5):
    with pytest.raises(ValueError) as err:
        _ = [b for b in chain_that_mined_5.blocks.range(-1, 3, step=2)]

    assert "Input should be greater than or equal to 0" in str(err.value)


def test_block_range_out_of_order(chain_that_mined_5):
    with pytest.raises(ValueError) as err:
        _ = [b for b in chain_that_mined_5.blocks.range(3, 1, step=2)]

    assert "stop_block: '0' cannot be less than start_block: '3'." in str(err.value)


def test_block_timestamp(chain):
    chain.mine()
    assert chain.blocks.head.timestamp == chain.blocks.head.datetime.timestamp()


def test_poll_blocks_stop_block_not_in_future(chain_that_mined_5):
    bad_stop_block = chain_that_mined_5.blocks.height

    with pytest.raises(ValueError, match="'stop' argument must be in the future."):
        _ = [x for x in chain_that_mined_5.blocks.poll_blocks(stop_block=bad_stop_block)]


def test_poll_blocks(chain_that_mined_5, eth_tester_provider, owner, PollDaemon):
    blocks: Queue = Queue(maxsize=3)
    poller = chain_that_mined_5.blocks.poll_blocks()

    with PollDaemon("blocks", poller, blocks.put, blocks.full):
        # Sleep first to ensure listening before mining.
        time.sleep(1)
        eth_tester_provider.mine(3)

    assert blocks.full()
    first = blocks.get().number
    second = blocks.get().number
    third = blocks.get().number
    assert first == second - 1
    assert second == third - 1


def test_poll_blocks_reorg(chain_that_mined_5, eth_tester_provider, owner, PollDaemon, ape_caplog):
    blocks: Queue = Queue(maxsize=6)
    poller = chain_that_mined_5.blocks.poll_blocks()

    with PollDaemon("blocks", poller, blocks.put, blocks.full):
        # Sleep first to ensure listening before mining.
        time.sleep(1)

        snapshot = chain_that_mined_5.snapshot()
        chain_that_mined_5.mine(2)

        # Wait to allow blocks before re-org to get yielded
        time.sleep(5)

        # Simulate re-org by reverting to the snapshot
        chain_that_mined_5.restore(snapshot)

        # Allow it time to trigger realizing there was a re-org
        time.sleep(1)
        chain_that_mined_5.mine(2)
        time.sleep(1)

        chain_that_mined_5.mine(3)

    assert blocks.full()

    # Show that re-org was detected
    expected_error = (
        "Chain has reorganized since returning the last block. "
        "Try adjusting the required network confirmations."
    )
    assert ape_caplog.records, "Didn't detect re-org"
    ape_caplog.assert_last_log(expected_error)

    # Show that there are duplicate blocks
    block_numbers: list[int] = [blocks.get().number for _ in range(6)]
    assert len(set(block_numbers)) < len(block_numbers)


def test_poll_blocks_timeout(
    vyper_contract_instance, chain_that_mined_5, eth_tester_provider, owner, PollDaemon
):
    poller = chain_that_mined_5.blocks.poll_blocks(new_block_timeout=1)

    with pytest.raises(ProviderError, match=r"Timed out waiting for next block."):
        with PollDaemon("blocks", poller, lambda x: None, lambda: False):
            time.sleep(1.5)


def test_poll_blocks_reorg_with_timeout(
    vyper_contract_instance, chain_that_mined_5, eth_tester_provider, owner, PollDaemon, ape_caplog
):
    blocks: Queue = Queue(maxsize=6)
    poller = chain_that_mined_5.blocks.poll_blocks(new_block_timeout=1)

    with pytest.raises(ProviderError, match=r"Timed out waiting for next block."):
        with PollDaemon("blocks", poller, blocks.put, blocks.full):
            # Sleep first to ensure listening before mining.
            time.sleep(1)

            snapshot = chain_that_mined_5.snapshot()
            chain_that_mined_5.mine(2)

            # Wait to allow blocks before re-org to get yielded
            time.sleep(5)

            # Simulate re-org by reverting to the snapshot
            chain_that_mined_5.restore(snapshot)

            # Allow it time to trigger realizing there was a re-org
            time.sleep(1)
            chain_that_mined_5.mine(2)
            time.sleep(1)

            chain_that_mined_5.mine(3)


def test_poll_blocks_future(chain_that_mined_5, eth_tester_provider, owner, PollDaemon):
    blocks: Queue = Queue(maxsize=3)
    poller = chain_that_mined_5.blocks.poll_blocks(
        start_block=chain_that_mined_5.blocks.head.number + 1
    )

    with PollDaemon("blocks", poller, blocks.put, blocks.full):
        # Sleep first to ensure listening before mining.
        time.sleep(1)
        eth_tester_provider.mine(3)

    assert blocks.full()
    first = blocks.get().number
    second = blocks.get().number
    third = blocks.get().number
    assert first == second - 1
    assert second == third - 1
