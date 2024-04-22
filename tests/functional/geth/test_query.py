from tests.conftest import geth_process_test


@geth_process_test
def test_get_contract_metadata(
    mock_geth, geth_contract, geth_account, chain, networks, geth_provider
):
    networks.active_provider = mock_geth
    actual = chain.contracts.get_creation_metadata(geth_contract.address)
    assert actual.deployer == geth_account.address

    # hold onto block, setup mock.
    block = geth_provider.get_block(actual.block)
    del chain.contracts._local_contract_creation[geth_contract.address]
    mock_geth.web3.eth.get_block.return_value = block

    orig_web3 = chain.network_manager.active_provider._web3
    chain.network_manager.active_provider._web3 = mock_geth.web3
    try:
        for client in ("geth", "erigon"):
            chain.network_manager.active_provider._client_version = client
            _ = chain.contracts.get_creation_metadata(geth_contract.address)
    finally:
        chain.network_manager.active_provider._web3 = orig_web3

    call_args = mock_geth._web3.provider.make_request.call_args_list

    # geth
    assert call_args[-2][0][0] == "debug_traceBlockByNumber"
    assert call_args[-2][0][1][1] == {"tracer": "callTracer"}
    # parity
    assert call_args[-1][0][0] == "trace_replayBlockTransactions"
    assert call_args[-1][0][1][1] == ["trace"]
