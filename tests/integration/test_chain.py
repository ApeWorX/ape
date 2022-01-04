import pytest

from ape.exceptions import ChainError
from ape.managers.chain import ChainManager


@pytest.fixture
def chain_manager(networks_connected_to_tester):
    manager = ChainManager(networks_connected_to_tester)
    yield manager

    # Head back to the initial block.
    while manager.block_number != 0:
        manager.restore()


def test_snapshot_and_restore(chain_manager, sender, receiver):
    initial_balance = receiver.balance  # Initial balance at block 0.
    end_range = 5
    snapshot_ids = []

    for i in range(0, end_range):
        snapshot_id = chain_manager.snapshot()
        snapshot_ids.append(snapshot_id)
        sender.transfer(receiver, "1 wei")  # Advance a block by transacting

    assert chain_manager.block_number == end_range

    # Show that we can also provide the snapshot ID as an argument.
    chain_manager.restore(snapshot_ids[2])
    assert chain_manager.block_number == 2

    # Head back to the initial block.
    while chain_manager.block_number != 0:
        chain_manager.restore()

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

    assert "Unknown snapshot_id" in str(err.value)


def test_snapshot_and_restore_no_snapshots(chain_manager, sender, receiver):
    with pytest.raises(ChainError) as err:
        chain_manager.restore("{}")

    assert "There are no snapshots to revert to." in str(err.value)
