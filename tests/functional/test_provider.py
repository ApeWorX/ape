def test_chain_id(eth_tester_provider):
    expected_chain_id = 61

    chain_id = eth_tester_provider.chain_id
    assert chain_id == expected_chain_id

    # Unset `_web3` to show that it is not used in a second call to `chain_id`.
    eth_tester_provider._web3 = None
    chain_id = eth_tester_provider.chain_id
    assert chain_id == expected_chain_id
