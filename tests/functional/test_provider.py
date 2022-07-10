import pytest

from ape.exceptions import ProviderError, ProviderNotConnectedError

EXPECTED_CHAIN_ID = 61


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


def test_get_transaction_not_exists_with_timeout(eth_tester_provider):
    unknown_txn = "0x053cba5c12172654d894f66d5670bab6215517a94189a9ffc09bc40a589ec04d"
    with pytest.raises(ProviderError) as err:
        eth_tester_provider.get_transaction(unknown_txn, timeout=0)

    assert f"Transaction '{unknown_txn}' not found" in str(err.value)


def test_get_transaction_exists_with_timeout(eth_tester_provider, vyper_contract_instance, owner):
    receipt_from_invoke = vyper_contract_instance.setNumber(123, sender=owner)
    receipt_from_provider = eth_tester_provider.get_transaction(
        receipt_from_invoke.txn_hash, timeout=0
    )
    assert receipt_from_provider.txn_hash == receipt_from_invoke.txn_hash
