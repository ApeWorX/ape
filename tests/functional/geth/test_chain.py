from tests.conftest import geth_process_test


@geth_process_test
def test_get_code(mocker, chain, geth_contract, mock_sepolia):
    # NOTE: Using mock_sepolia because code doesn't get cached in local networks.
    actual = chain.get_code(geth_contract.address)
    expected = chain.provider.get_code(geth_contract.address)
    assert actual == expected

    # Ensure uses cache (via not using provider).
    provider_spy = mocker.spy(chain.provider.web3.eth, "get_code")
    _ = chain.get_code(geth_contract.address)
    assert provider_spy.call_count == 0

    # block_id test, cache should interfere.
    actual_2 = chain.get_code(geth_contract.address, block_id=0)
    assert not actual_2  # Doesn't exist at block 0.
