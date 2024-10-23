from collections import defaultdict
from datetime import datetime, timedelta

import pytest

from ape.exceptions import APINotImplementedError, ChainError, UnknownSnapshotError
from ape.managers.chain import AccountHistory
from ape.types.address import AddressType


def test_snapshot_and_restore(chain, owner, receiver, vyper_contract_instance):
    initial_balance = receiver.balance  # Initial balance at block 0.
    blocks_to_mine = 5
    snapshot_ids = []

    # Since this receipt is before the snapshotting, it will be present after restoring
    receipt_to_keep = vyper_contract_instance.setNumber(3, sender=owner)
    checkpoint_nonce = owner.nonce  # Will restore here.

    start_block = chain.blocks.height
    for i in range(blocks_to_mine):
        snapshot_id = chain.snapshot()
        snapshot_ids.append(snapshot_id)
        chain.mine()

    # Since this receipt is after snapshotting, it will be gone after restoring

    assert chain.blocks[-1].number == start_block + blocks_to_mine
    receipt_to_lose = vyper_contract_instance.setNumber(3, sender=owner)

    # Increase receiver's balance
    owner.transfer(receiver, "123 wei")

    # Show that we can also provide the snapshot ID as an argument.
    restore_index = 2
    chain.restore(snapshot_ids[restore_index])

    # The nonce is the same as it when we snapshotted.
    assert owner.nonce == checkpoint_nonce

    assert chain.blocks[-1].number == start_block + restore_index

    # Verify we lost and kept the expected transaction hashes from the account history
    owner_txns = [x.txn_hash for x in owner.history]
    assert receipt_to_keep.txn_hash in owner_txns
    assert receipt_to_lose.txn_hash not in owner_txns

    # Head back to the start block
    chain.restore(snapshot_ids[0])
    assert chain.blocks[-1].number == start_block
    assert receiver.balance == initial_balance


def test_snapshot_and_restore_unknown_snapshot_id(chain):
    _ = chain.snapshot()
    chain.mine()
    snapshot_id_2 = chain.snapshot()
    chain.mine()
    snapshot_id_3 = chain.snapshot()
    chain.mine()

    # After restoring to the second ID, the third ID is now invalid.
    chain.restore(snapshot_id_2)

    with pytest.raises(UnknownSnapshotError) as err:
        chain.restore(snapshot_id_3)

    assert "Unknown snapshot ID" in str(err.value)


def test_snapshot_and_restore_no_snapshots(chain):
    chain._snapshots = defaultdict(list)  # Ensure empty (gets set in test setup)
    with pytest.raises(ChainError, match="There are no snapshots to revert to."):
        chain.restore()


def test_snapshot_and_restore_switched_chains(networks, chain):
    """
    Ensuring things work as expected when we switch chains after snapshotting
    and before restoring.
    """
    snapshot = chain.snapshot()
    # Switch chains.
    with networks.ethereum.local.use_provider(
        "test", provider_settings={"chain_id": 11191919191991918223773}
    ):
        with pytest.raises(UnknownSnapshotError):
            chain.restore(snapshot)


def test_isolate(chain, vyper_contract_instance, owner):
    number_at_start = 444
    vyper_contract_instance.setNumber(number_at_start, sender=owner)
    start_head = chain.blocks.height

    with chain.isolate():
        vyper_contract_instance.setNumber(333, sender=owner)
        assert vyper_contract_instance.myNumber() == 333
        assert chain.blocks.height == start_head + 1

    assert chain.blocks.height == start_head
    assert vyper_contract_instance.myNumber() == number_at_start


def test_history_uses_cache(mocker, eth_tester_provider, chain, vyper_contract_instance, owner):
    expected = vyper_contract_instance.setNumber(3, sender=owner)
    eth = eth_tester_provider.web3.eth
    rpc_spy = mocker.spy(eth, "get_transaction")
    actual = chain.get_receipt(expected.txn_hash)
    assert actual.txn_hash == expected.txn_hash
    assert actual.sender == expected.sender
    assert actual.receiver == expected.receiver
    assert not rpc_spy.call_count

    # Show it uses the provider when the receipt is not cached.
    del chain.history._hash_to_receipt_map[expected.txn_hash]
    chain.get_receipt(expected.txn_hash)
    assert rpc_spy.call_count == 1

    # Show it is cached after the first time
    chain.get_receipt(expected.txn_hash)
    assert rpc_spy.call_count == 1  # Not changed


def test_history_getitem_receipt(chain, vyper_contract_instance, owner):
    expected = vyper_contract_instance.setNumber(3, sender=owner)
    actual = chain.history[expected.txn_hash]
    assert actual.txn_hash == expected.txn_hash
    assert actual.sender == expected.sender
    assert actual.receiver == expected.receiver


def test_history_getitem_account(chain, vyper_contract_instance, owner):
    actual = chain.history[owner.address]
    assert isinstance(actual, AccountHistory)
    assert actual.address == owner.address


def test_history_getitem_account_ens(mocker, chain, vyper_contract_instance, owner):
    conversion_spy = mocker.spy(chain.history.conversion_manager, "convert")
    value = "this will not work, but would if given ens and using ape-ens"
    expected_err = rf"'{value}' is not a known address or transaction hash\."
    with pytest.raises(ChainError, match=expected_err):
        _ = chain.history[value]

    conversion_spy.assert_called_once_with(value, AddressType)


def test_set_pending_timestamp(chain):
    start_timestamp = chain.pending_timestamp
    chain.pending_timestamp += 3600
    new_timestamp = chain.pending_timestamp
    assert new_timestamp - start_timestamp == 3600


def test_set_pending_timestamp_with_deltatime(chain):
    start_timestamp = chain.pending_timestamp
    chain.mine(deltatime=5)
    new_timestamp = chain.pending_timestamp
    actual = new_timestamp - start_timestamp - 5
    assert actual <= 1


def test_set_pending_timestamp_failure(chain):
    with pytest.raises(
        ValueError, match="Cannot give both `timestamp` and `deltatime` arguments together."
    ):
        chain.mine(
            timestamp=int(datetime.now().timestamp() + timedelta(seconds=10).seconds),
            deltatime=10,
        )


def test_set_balance(chain, owner):
    with pytest.raises(APINotImplementedError):
        chain.set_balance(owner, "1000 ETH")
