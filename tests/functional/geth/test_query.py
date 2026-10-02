from eth_utils import to_hex

from ape_cache.query import CacheQueryProvider
from ape_ethereum.ecosystem import Block
from tests.conftest import geth_process_test


def _hex(value: object) -> str:
    return value.lower() if isinstance(value, str) else to_hex(value).lower()


def test_mainnet_history_is_served_from_the_file_cache(
    chain, networks, monkeypatch, mocker, tmp_path
):
    # Keep the file cache in a temp folder so this test does not write into
    # the shared data directory.
    def cache_folder(self, ecosystem_name=None, network_name=None):
        if ecosystem_name is None or network_name is None:
            ecosystem_name = self.provider.network.ecosystem.name
            network_name = self.provider.network.name

        return tmp_path / ecosystem_name / network_name / "query-cache"

    monkeypatch.setattr(CacheQueryProvider, "cache_folder", cache_folder)

    with networks.ethereum.mainnet.use_provider("node") as provider:
        assert provider.chain_id == 1
        # Public mainnet nodes often prune ancient blocks. Stay behind head so the
        # window is sealed history that a pruned node still serves.
        stop = chain.blocks.height - 256
        start = stop - 3
        prefix_stop = start + 1
        assert start > 15_000_000
        cache_dir = cache_folder(chain.query_manager.engines["cache"]) / "blocks" / ".number"
        assert "mainnet" in cache_dir.parts

        prefix = chain.blocks.query(
            "number", "hash", "timestamp", start_block=start, stop_block=prefix_stop
        )
        assert [int(number) for number in prefix["number"].to_list()] == list(
            range(start, prefix_stop + 1)
        )
        assert int(prefix["timestamp"][0]) > 1_600_000_000
        assert sorted(int(path.name) for path in cache_dir.iterdir()) == list(
            range(start, prefix_stop + 1)
        )

        stored = Block.model_validate_json((cache_dir / str(start)).read_text())
        live = provider.get_block(start)
        assert stored.number is not None
        assert int(stored.number) == start
        assert _hex(stored.hash) == _hex(live.hash)
        assert int(stored.timestamp) == int(live.timestamp)

        # The cached prefix stays on disk. Only the tail should hit the node.
        # Spy the RPC the provider uses. The node provider is a pydantic model,
        # so spying its get_block method cannot be torn down.
        get_block = mocker.spy(provider.web3.eth, "get_block")
        full = chain.blocks.query("number", "hash", start_block=start, stop_block=stop)
        fetched = [
            call.args[0]
            for call in get_block.call_args_list
            if call.args and isinstance(call.args[0], int)
        ]
        assert [int(number) for number in full["number"].to_list()] == list(range(start, stop + 1))
        prefix_len = prefix_stop - start + 1
        assert [_hex(value) for value in full["hash"].to_list()[:prefix_len]] == [
            _hex(value) for value in prefix["hash"].to_list()
        ]
        assert fetched
        assert set(fetched).isdisjoint(range(start, prefix_stop + 1))
        assert set(range(prefix_stop + 1, stop + 1)).issubset(fetched)
        assert sorted(int(path.name) for path in cache_dir.iterdir()) == list(
            range(start, stop + 1)
        )

        get_block.reset_mock()
        cached = chain.blocks.query("number", "hash", start_block=start, stop_block=stop)
        assert [int(number) for number in cached["number"].to_list()] == list(
            range(start, stop + 1)
        )
        assert [_hex(value) for value in cached["hash"].to_list()] == [
            _hex(value) for value in full["hash"].to_list()
        ]
        # Those historical numbers come from disk. A head lookup ("latest") is separate.
        assert {call.args[0] for call in get_block.call_args_list} <= {"latest"}


@geth_process_test
def test_get_contract_metadata(
    mock_geth, geth_contract, geth_account, chain, networks, geth_provider
):
    networks.active_provider = mock_geth
    actual = chain.contracts.get_creation_metadata(geth_contract.address)
    assert actual.deployer == geth_account.address

    # hold onto block, setup mock.
    block = geth_provider.get_block(actual.block)
    del chain.contracts.contract_creations[geth_contract.address]
    mock_geth.web3.eth.get_block.return_value = block

    orig_web3 = chain.network_manager.active_provider._web3
    chain.network_manager.active_provider._web3 = mock_geth.web3
    try:
        for client in ("geth", "erigon"):
            chain.network_manager.active_provider._client_version = client
            _ = chain.contracts.get_creation_metadata(geth_contract.address)
    finally:
        chain.network_manager.active_provider._web3 = orig_web3

    # The cursor checks that the RPC method exists before tracing, so those
    # probes use an empty argument list. The search itself carries the tracer.
    def traced(method: str) -> list:
        return [
            call.args
            for call in mock_geth._web3.provider.make_request.call_args_list
            if call.args and call.args[0] == method and len(call.args) > 1 and call.args[1]
        ]

    debug = traced("debug_traceBlockByNumber")
    parity = traced("trace_replayBlockTransactions")
    assert len(debug) == 1
    assert debug[0][1][1] == {"tracer": "callTracer"}
    assert len(parity) == 1
    assert parity[0][1][1] == ["trace"]
