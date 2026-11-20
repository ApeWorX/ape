import pytest

from ape.exceptions import ChainError
from ape_ethereum.transactions import Receipt, TransactionStatusEnum
from tests.conftest import explorer_test


def test_history(sender, receiver, chain):
    length_at_start = len(chain.history[sender].sessional)
    receipt = sender.transfer(receiver, 1)
    transactions_from_cache = list(sender.history)
    assert len(transactions_from_cache) == length_at_start + 1
    assert sender.history[-1] == receipt
    assert sender.history[0:] == transactions_from_cache[0:]
    assert sender.history[:-1] == transactions_from_cache[:-1]

    txn = transactions_from_cache[-1]
    assert txn.sender == receipt.sender == sender
    assert txn.receiver == receipt.receiver == receiver


@pytest.mark.parametrize(
    "index",
    (slice(None, 0), slice(0, 0), slice(None, None, -1), slice(None, None, 2), slice(1, 3)),
)
def test_history_slice_access_matches_list(sender, receiver, index):
    # Need a few transactions for steps and reversal to be meaningful.
    while len(sender.history) < 3:
        sender.transfer(receiver, 1)

    expected = list(sender.history)[index]
    assert [r.txn_hash for r in sender.history[index]] == [r.txn_hash for r in expected]


def test_history_slice_access_stop_greater_than_nonce(sender):
    with pytest.raises(ChainError, match="cannot be greater than account's current nonce"):
        _ = sender.history[: len(sender.history) + 1]


def test_history_slice_access_sparse_query_result(mocker, sender, receiver):
    # A query engine is not guaranteed to answer with exactly one receipt per nonce
    # in the requested span, so receipts must be selected by their own nonce and
    # not by their position in the result.
    while len(sender.history) < 4:
        sender.transfer(receiver, 1)

    receipts = list(sender.history)[:4]
    assert [r.nonce for r in receipts] == [0, 1, 2, 3]
    query_manager = mocker.MagicMock()
    query_manager.query.side_effect = lambda *a, **k: iter(
        [r for r in receipts if r.nonce != 1]  # The engine skips nonce 1.
    )
    mocker.patch.object(type(sender.history), "query_manager", query_manager)

    # Nonce 1 is simply absent; nonce 2 is not mistaken for nonce 3.
    assert [r.nonce for r in sender.history[0:4]] == [0, 2, 3]
    assert [r.nonce for r in sender.history[0:4:2]] == [0, 2]
    assert [r.nonce for r in sender.history[3:0:-1]] == [3, 2]


@explorer_test
def test_history_caches_sender_over_address_key(
    chain, eth_tester_provider, sender, project, ethereum, mock_explorer
):
    # When getting receipts from the explorer for contracts, it includes transactions
    # made to the contract. This test shows we cache by sender and not address key.
    contract = sender.deploy(project.VyperContract, 0)
    network = ethereum.local
    txn = ethereum.create_transaction(
        receiver=contract.address, sender=sender.address, value=10000000000000000000000
    )
    known_receipt = Receipt(
        block_number=10,
        gas_price=11,
        gas_used=12,
        gas_limit=13,
        status=TransactionStatusEnum.NO_ERROR.value,
        txn_hash="0x98d2aee8617897b5983314de1d6ff44d1f014b09575b47a88267971beac97b2b",
        transaction=txn,
    )

    # The receipt is already known and cached by the sender.
    chain.history.append(known_receipt)

    # We ask for receipts from the contract, but it returns ones sent to the contract.
    def get_txns_patch(address):
        if address == contract.address:
            yield from [known_receipt]

    mock_explorer.get_account_transactions.side_effect = get_txns_patch
    network.__dict__["explorer"] = mock_explorer
    eth_tester_provider.network = network

    # Previously, this would error because the receipt was cached with the wrong sender
    try:
        actual = [t for t in chain.history[contract.address].sessional]

        # Actual is 0 because the receipt was cached under the sender.
        assert len(actual) == 0
    finally:
        network.__dict__.pop("explorer", None)
