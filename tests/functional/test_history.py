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


@explorer_test
def test_history_caches_sender_over_address_key(
    chain, eth_tester_provider, sender, vyper_contract_container, ethereum, mock_explorer
):
    # When getting receipts from the explorer for contracts, it includes transactions
    # made to the contract. This test shows we cache by sender and not address key.
    contract = sender.deploy(vyper_contract_container, 0)
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
        if "explorer" in network.__dict__:
            del network.__dict__["explorer"]
