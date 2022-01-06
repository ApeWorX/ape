import pytest

from ape.exceptions import ChainError
from ape.managers.chain import ChainManager


@pytest.fixture
def chain_manager(networks):
    manager = ChainManager(networks)
    return manager


@pytest.fixture
def chain_manager_up_5_blocks(chain_manager, sender, receiver):
    snapshot_id = chain_manager.snapshot()
    for i in range(5):
        sender.transfer(receiver, "1 wei")

    yield chain_manager
    chain_manager.restore(snapshot_id)


def test_snapshot_and_restore(chain_manager, sender, receiver):
    initial_balance = receiver.balance  # Initial balance at block 0.
    end_range = 5
    snapshot_ids = []

    for i in range(end_range):
        snapshot_id = chain_manager.snapshot()
        snapshot_ids.append(snapshot_id)
        sender.transfer(receiver, "1 wei")  # Advance a block by transacting

    assert chain_manager.blocks[-1].number == end_range

    # Show that we can also provide the snapshot ID as an argument.
    chain_manager.restore(snapshot_ids[2])
    assert chain_manager.blocks[-1].number == 2

    # Head back to the initial block.
    while chain_manager.blocks[-1].number != 0:
        chain_manager.restore()

    assert chain_manager.blocks[-1].number == 0
    assert receiver.balance == initial_balance


def test_snapshot_and_restore_unknown_snapshot_id(chain_manager, sender, receiver):
    _ = chain_manager.snapshot()
    sender.transfer(receiver, "1 wei")
    snapshot_id_2 = chain_manager.snapshot()
    sender.transfer(receiver, "1 wei")
    snapshot_id_3 = chain_manager.snapshot()
    sender.transfer(receiver, "1 wei")

    # After restoring to the second ID, the third ID is now invalid.
    chain_manager.restore(snapshot_id_2)

    with pytest.raises(ChainError) as err:
        chain_manager.restore(snapshot_id_3)

    assert "Unknown snapshot ID" in str(err.value)


def test_snapshot_and_restore_no_snapshots(chain_manager, sender, receiver):
    with pytest.raises(ChainError) as err:
        chain_manager.restore("{}")

    assert "There are no snapshots to revert to." in str(err.value)


def test_account_history(sender, receiver, chain_manager):
    history = chain_manager.account_history
    assert not history[sender]
    receipt = sender.transfer(receiver, "1 wei")
    transactions_from_cache = history[sender]
    assert len(transactions_from_cache) == 1

    txn = transactions_from_cache[0]
    assert txn.sender == receipt.sender == sender
    assert txn.receiver == receipt.receiver == receiver


def test_iterate_blocks(chain_manager_up_5_blocks):
    expected_number_of_blocks = 6  # Including the 0th start block
    blocks = [b for b in chain_manager_up_5_blocks.blocks]
    assert len(blocks) == expected_number_of_blocks

    expected_number = 0
    for block in blocks:
        assert block.number == expected_number
        expected_number += 1


def test_blocks_range(chain_manager_up_5_blocks):
    expected_number_of_blocks = 3  # Expecting blocks [0, 1, 2]
    blocks = [b for b in chain_manager_up_5_blocks.blocks.range(stop=3)]
    assert len(blocks) == expected_number_of_blocks

    expected_number = 0
    for block in blocks:
        assert block.number == expected_number
        expected_number += 1
