import json
import time
from types import SimpleNamespace
from typing import Any, cast

import narwhals.stable.v2 as nw
import pytest
from ethpm_types.abi import EventABI, MethodABI

from ape.api import query as query_api
from ape.api.query import (
    BlockQuery,
    ContractEventQuery,
    ContractMethodQuery,
    to_dataframe,
    validate_and_expand_columns,
)
from ape.exceptions import QueryEngineError
from ape.managers.query import QueryManager, QueryResult
from ape.utils import DEFAULT_TEST_CHAIN_ID, BaseInterfaceModel
from ape_cache.query import CacheQueryProvider
from ape_ethereum.ecosystem import Block


def test_basic_query(chain, eth_tester_provider):
    chain.mine(3)
    blocks_df0 = chain.blocks.query("*")
    blocks_df1 = chain.blocks.query("number", "timestamp")

    assert blocks_df0["number"].to_list()[:4] == [0, 1, 2, 3]
    assert len(blocks_df1) == len(chain.blocks)
    assert (
        blocks_df1["timestamp"][3]
        >= blocks_df1["timestamp"][2]
        >= blocks_df1["timestamp"][1]
        >= blocks_df1["timestamp"][0]
    )
    assert blocks_df0.columns == [
        "base_fee",
        "difficulty",
        "gas_limit",
        "gas_used",
        "hash",
        "num_transactions",
        "number",
        "parent_hash",
        "timestamp",
        "total_difficulty",
        "uncles",
    ]


def test_relative_block_query(chain, eth_tester_provider):
    start_block = chain.blocks.height
    chain.mine(10)
    df = chain.blocks.query("*", start_block=-8, stop_block=-2)
    assert len(df) == 7
    assert df["number"].min() == chain.blocks[-8].number == start_block + 3
    assert df["number"].max() == chain.blocks[-2].number == start_block + 9


def test_block_transaction_query(chain, eth_tester_provider, sender, receiver):
    sender.transfer(receiver, 100)
    query = chain.blocks[-1].transactions
    assert len(query) == 1
    assert query[0].value == 100
    assert query[0].chain_id == DEFAULT_TEST_CHAIN_ID


def test_transaction_contract_event_query(contract_instance, owner, eth_tester_provider):
    contract_instance.fooAndBar(sender=owner)
    time.sleep(0.1)
    df_events = contract_instance.FooHappened.query("*", start_block=-1)
    assert isinstance(df_events, nw.DataFrame)
    assert df_events["event_name"][0] == "FooHappened"
    assert df_events.columns[-1] == "foo"
    assert int(df_events["foo"][0]) == 0

    picked = contract_instance.FooHappened.query("foo", "event_name", start_block=-1)
    assert picked.columns == ["foo", "event_name"]
    assert int(picked["foo"][0]) == 0


def test_transaction_contract_event_query_starts_query_at_deploy_tx(
    contract_instance, owner, eth_tester_provider
):
    contract_instance.fooAndBar(sender=owner)
    time.sleep(0.1)
    df_events = contract_instance.FooHappened.query("*")
    assert isinstance(df_events, nw.DataFrame)
    assert df_events["event_name"][0] == "FooHappened"


def test_account_history_query(sender, receiver, eth_tester_provider):
    receipt = sender.transfer(receiver, 100)
    # The next nonce is len(history). The transfer itself is receipt.nonce.
    df = sender.history.query("nonce", "value", stop_nonce=receipt.nonce)
    assert isinstance(df, nw.DataFrame)
    assert [int(value) for value in df["nonce"].to_list()] == [int(receipt.nonce)]
    assert [int(value) for value in df["value"].to_list()] == [100]


def test_block_query_step(chain, eth_tester_provider):
    start = chain.blocks.height
    chain.mine(4)
    stop = chain.blocks.height
    numbers = chain.blocks.query("number", start_block=start, stop_block=stop, step=2)[
        "number"
    ].to_list()
    assert [int(number) for number in numbers] == list(range(start, stop + 1, 2))


def test_contract_creation_metadata_reads_as_a_frame(chain, vyper_contract_instance, owner):
    creation = vyper_contract_instance.creation_metadata
    assert creation is not None
    assert creation.deployer == owner.address

    frame = to_dataframe(
        {
            "txn_hash": [creation.txn_hash],
            "block": [creation.block],
            "deployer": [creation.deployer],
        },
        None,
        chain.config_manager.query.backend,
    )
    assert isinstance(frame, nw.DataFrame)
    assert frame["txn_hash"].to_list() == [creation.txn_hash]
    assert int(frame["block"][0]) == creation.block
    assert frame["deployer"][0] == owner.address


def test_contract_creation_query_is_empty_without_traces(chain, vyper_contract_instance):
    # Eth-tester has no trace API. The deploy cache is the creation record;
    # asking the engine after that cache is cleared returns nothing.
    address = vyper_contract_instance.address
    del chain.contracts.contract_creations[address]
    assert chain.contracts.get_creation_metadata(address) is None


class Model(BaseInterfaceModel):
    number: int
    timestamp: int


def test_column_expansion():
    columns = validate_and_expand_columns(["*"], Model)
    assert columns == list(Model.model_fields)


def test_column_validation(eth_tester_provider, ape_caplog):
    with pytest.raises(ValueError) as exc_info:
        validate_and_expand_columns(["numbr"], Model)

    expected = "Unrecognized field(s) 'numbr', must be one of 'number, timestamp'."
    assert exc_info.value.args[-1] == expected

    ape_caplog.assert_last_log_with_retries(
        lambda: validate_and_expand_columns(["numbr", "timestamp"], Model), expected
    )

    validate_and_expand_columns(["number", "timestamp", "number"], Model)
    assert "Duplicate fields in ['number', 'timestamp', 'number']" in ape_caplog.messages[-1]


def test_query_uses_configured_dataframe_backend():
    frame = to_dataframe({"number": [1]}, None, "pandas")
    assert frame.get_column("number").to_list() == [1]


def test_query_autodetects_installed_backend():
    frame = to_dataframe({"number": [1]}, None, None)
    assert frame.get_column("number").to_list() == [1]


def test_query_prefers_polars_when_installed(monkeypatch):
    monkeypatch.setattr(
        query_api,
        "find_spec",
        lambda name: object() if name in {"polars", "pandas"} else None,
    )
    query_api._detected_dataframe_backend.cache_clear()
    try:
        assert query_api._detected_dataframe_backend() is nw.Implementation.POLARS
    finally:
        query_api._detected_dataframe_backend.cache_clear()


def test_query_hands_off_to_polars_when_pandas_is_installed(chain, eth_tester_provider):
    import pandas as pd
    import polars as pl

    chain.mine(1)
    default = chain.blocks.query("number")
    explicit = chain.blocks.query("number", backend="pandas")

    assert isinstance(default.to_native(), pl.DataFrame)
    assert isinstance(explicit.to_native(), pd.DataFrame)
    assert explicit.get_column("number").to_list() == default.get_column("number").to_list()


def test_query_requires_a_dataframe_library(monkeypatch):
    monkeypatch.setattr(query_api, "_detected_dataframe_backend", lambda: None)
    with pytest.raises(QueryEngineError, match="needs a dataframe library"):
        to_dataframe({"number": [0]}, None, None)


def test_query_unknown_dataframe_backend():
    with pytest.raises(QueryEngineError, match="not a Narwhals dataframe backend"):
        to_dataframe({"number": [0]}, "not-a-library", None)


def test_query_missing_dataframe_library():
    with pytest.raises(QueryEngineError, match="not installed"):
        to_dataframe({"number": [0]}, "cudf", None)


class _Window:
    def __init__(self, start, end, step=1):
        self.start_index = start
        self.end_index = end
        self.step = step


class _Cursor:
    def __init__(self, start, end, cost, step=1, shrinkable=True, total_time=None):
        self.query = _Window(start, end, step)
        self.time_per_row = cost
        self.total_time = cost if total_time is None else total_time
        self.shrinkable = shrinkable

    def shrink(self, start_index=None, end_index=None):
        start = self.query.start_index if start_index is None else start_index
        end = self.query.end_index if end_index is None else end_index
        if not self.shrinkable and (start != self.query.start_index or end != self.query.end_index):
            raise NotImplementedError

        return _Cursor(start, end, self.time_per_row, self.query.step, self.shrinkable)


def _solve(query, cursors):
    return list(QueryManager._solve_optimal_coverage(query, cursors))


def test_solver_prefers_one_cheap_cursor():
    query = _Window(0, 10)
    fast = _Cursor(0, 10, cost=0.01)
    slow = _Cursor(0, 5, cost=0.5)
    pieces = _solve(query, [fast, slow])
    assert [(piece.query.start_index, piece.query.end_index) for piece in pieces] == [(0, 10)]


def test_solver_stitches_abutting_ranges():
    query = _Window(0, 10)
    pieces = _solve(query, [_Cursor(0, 4, cost=1), _Cursor(5, 10, cost=1)])
    assert [(piece.query.start_index, piece.query.end_index) for piece in pieces] == [
        (0, 4),
        (5, 10),
    ]


def test_solver_single_index_is_not_inverted():
    query = _Window(3, 3)
    pieces = _solve(query, [_Cursor(3, 3, cost=1)])
    assert [(piece.query.start_index, piece.query.end_index) for piece in pieces] == [(3, 3)]


def test_solver_empty_query_yields_nothing():
    assert _solve(_Window(5, 4), [_Cursor(0, 10, cost=1)]) == []


def test_solver_missing_coverage_raises():
    with pytest.raises(QueryEngineError, match=r"missing coverage in window \[5:10\]"):
        _solve(_Window(0, 10), [_Cursor(0, 4, cost=1)])


def test_solver_merges_adjacent_segments_of_the_same_cursor():
    query = _Window(0, 10)
    wide = _Cursor(0, 10, cost=1)
    # The partial cursor only adds a boundary. It loses both segments on cost.
    pieces = _solve(query, [wide, _Cursor(0, 5, cost=5)])
    assert [(piece.query.start_index, piece.query.end_index) for piece in pieces] == [(0, 10)]


def test_solver_breaks_ties_on_total_time():
    query = _Window(0, 10)
    pieces = _solve(
        query,
        [
            _Cursor(0, 10, cost=1, total_time=100),
            _Cursor(0, 10, cost=1, total_time=1),
        ],
    )
    assert [(piece.query.start_index, piece.query.end_index) for piece in pieces] == [(0, 10)]
    assert pieces[0].total_time == 1


def test_solver_uses_a_rigid_cursor_for_its_whole_window():
    pieces = _solve(_Window(0, 10), [_Cursor(0, 10, cost=1, shrinkable=False)])
    assert [(piece.query.start_index, piece.query.end_index) for piece in pieces] == [(0, 10)]


def test_solver_keeps_a_rigid_cursor_on_its_exact_segment():
    pieces = _solve(
        _Window(0, 10),
        [_Cursor(0, 4, cost=1, shrinkable=False), _Cursor(5, 10, cost=1)],
    )
    assert [(piece.query.start_index, piece.query.end_index) for piece in pieces] == [
        (0, 4),
        (5, 10),
    ]


def test_solver_cannot_cut_a_rigid_cursor():
    # A boundary inside a cursor that refuses to shrink drops that cursor.
    with pytest.raises(QueryEngineError, match=r"missing coverage in window \[5:10\]"):
        _solve(
            _Window(0, 10),
            [_Cursor(0, 10, cost=1, shrinkable=False), _Cursor(0, 4, cost=5)],
        )


def test_solver_ignores_off_grid_cursor_edges():
    query = _Window(0, 10, step=2)
    pieces = _solve(query, [_Cursor(0, 10, cost=1, step=2), _Cursor(1, 9, cost=0.01, step=2)])
    assert [(piece.query.start_index, piece.query.end_index) for piece in pieces] == [(0, 10)]


def test_solver_splits_on_the_step_grid():
    pieces = _solve(
        _Window(0, 10, step=2),
        [_Cursor(0, 10, cost=1, step=2), _Cursor(4, 10, cost=0.1, step=2)],
    )
    assert [(piece.query.start_index, piece.query.end_index) for piece in pieces] == [
        (0, 2),
        (4, 10),
    ]


def test_solver_clips_a_cursor_wider_than_the_query():
    pieces = _solve(_Window(2, 8), [_Cursor(0, 20, cost=1)])
    assert [(piece.query.start_index, piece.query.end_index) for piece in pieces] == [(2, 8)]


def test_solver_ignores_a_cursor_outside_the_query():
    pieces = _solve(_Window(0, 10), [_Cursor(0, 10, cost=1), _Cursor(20, 30, cost=0.01)])
    assert [(piece.query.start_index, piece.query.end_index) for piece in pieces] == [(0, 10)]


def test_solver_outside_cursor_is_not_coverage():
    with pytest.raises(QueryEngineError, match=r"missing coverage in window \[0:10\]"):
        _solve(_Window(0, 10), [_Cursor(20, 30, cost=1)])


def test_solver_uses_a_cheap_middle_between_the_same_wide_cursor():
    pieces = _solve(_Window(0, 10), [_Cursor(0, 10, cost=1), _Cursor(3, 6, cost=0.1)])
    assert [(piece.query.start_index, piece.query.end_index) for piece in pieces] == [
        (0, 2),
        (3, 6),
        (7, 10),
    ]


def _coverage(query, cursors):
    # The validator is a Pydantic descriptor. Call the wrapped check with a stand-in result.
    result = SimpleNamespace(query=query, cursors=cursors)
    validate = cast(Any, QueryResult.validate_coverage)
    assert validate(result) is result
    return result


def test_validate_coverage_accepts_abutting_cursors():
    query = _Window(0, 10)
    cursors = [_Cursor(0, 4, cost=1), _Cursor(5, 10, cost=1)]
    result = _coverage(query, cursors)
    assert result.query is query
    assert result.cursors is cursors


def test_validate_coverage_follows_the_step():
    query = _Window(0, 10, step=2)
    cursors = [_Cursor(0, 2, cost=1), _Cursor(4, 10, cost=1)]
    assert _coverage(query, cursors).query is query


def test_validate_coverage_accepts_an_empty_query_with_no_cursors():
    query = _Window(5, 4)
    assert _coverage(query, []).query is query


def test_validate_coverage_rejects_cursors_on_an_empty_query():
    with pytest.raises(QueryEngineError, match="empty but has cursors"):
        _coverage(_Window(5, 4), [_Cursor(0, 0, cost=1)])


def test_validate_coverage_rejects_an_empty_cursor_window():
    with pytest.raises(QueryEngineError, match="empty window"):
        _coverage(_Window(0, 10), [_Cursor(0, -1, cost=1)])


def test_validate_coverage_rejects_a_gap():
    with pytest.raises(AssertionError, match="starts at 6, expected 5"):
        _coverage(_Window(0, 10), [_Cursor(0, 4, cost=1), _Cursor(6, 10, cost=1)])


def test_validate_coverage_rejects_an_overlap():
    with pytest.raises(AssertionError, match="starts at 4, expected 6"):
        _coverage(_Window(0, 10), [_Cursor(0, 5, cost=1), _Cursor(4, 10, cost=1)])


def test_validate_coverage_rejects_a_short_plan():
    with pytest.raises(AssertionError, match="ended at 4, expected 10"):
        _coverage(_Window(0, 10), [_Cursor(0, 4, cost=1)])


def test_result_time_per_row_is_zero_without_rows():
    query = BlockQuery(columns=["number"], start_block=0, stop_block=0)
    result = QueryResult.model_construct(query=query, cursors=[])
    assert result.time_per_row == 0.0


def test_event_query_expands_argument_columns():
    event = EventABI.model_validate(
        {
            "type": "event",
            "name": "Transfer",
            "inputs": [
                {"name": "src", "type": "address", "indexed": True},
                {"name": "dst", "type": "address", "indexed": True},
                {"name": "wad", "type": "uint256"},
                {"name": "block_number", "type": "uint256"},
                {"name": "", "type": "uint256"},
            ],
        }
    )
    query = ContractEventQuery(
        columns=["*"],
        contract="0x" + "00" * 20,
        event=event,
        start_block=1,
        stop_block=2,
    )
    assert query.columns[-3:] == ["src", "dst", "wad"]
    assert "event_arguments" in query.columns
    assert query.columns.count("block_number") == 1

    picked = ContractEventQuery(
        columns=["wad", "src", "wad"],
        contract="0x" + "00" * 20,
        event=event,
        start_block=1,
        stop_block=2,
    )
    assert picked.columns == ["wad", "src"]


def test_columns_keep_caller_order():
    query = BlockQuery(columns=["timestamp", "number"], start_block=0, stop_block=1)
    assert query.columns[:2] == ["timestamp", "number"]


def test_method_query_columns_are_not_block_fields():
    method = MethodABI.model_validate(
        {"type": "function", "name": "foo", "inputs": [], "outputs": [], "stateMutability": "view"}
    )
    query = ContractMethodQuery(
        columns=["foo_return"],
        contract="0x" + "00" * 20,
        method=method,
        method_args={},
        start_block=0,
        stop_block=1,
    )
    assert query.columns == ["foo_return"]


def test_block_cache_does_not_fetch_transactions(tmp_path, monkeypatch):
    monkeypatch.setattr(CacheQueryProvider, "cache_folder", lambda self, *args, **kwargs: tmp_path)
    block = Block.model_validate(
        {
            "gasLimit": 1,
            "gasUsed": 0,
            "hash": "0x" + "11" * 32,
            "number": 7,
            "parentHash": "0x" + "00" * 32,
            "timestamp": 1,
            "num_transactions": 4,
            "size": 1,
        }
    )
    query = BlockQuery(columns=["number"], start_block=7, stop_block=7)
    result = SimpleNamespace(query=query, as_model_iter=lambda: iter([block]))

    CacheQueryProvider().cache(result)

    payload = json.loads((tmp_path / "blocks" / ".number" / "7").read_text())
    assert "transactions" not in payload
    assert payload["number"] == 7
    assert payload["num_transactions"] == 4


def test_find_ranges_keeps_cached_runs(tmp_path):
    index = tmp_path / ".number"
    index.mkdir()
    for number in (1, 2, 3, 5):
        (index / str(number)).write_text("{}")

    assert list(CacheQueryProvider.find_ranges(index, start=0, end=10)) == [(1, 3), (5, 5)]
    assert list(CacheQueryProvider.find_ranges(index, start=0, end=0)) == []


def test_specify_engine(chain, eth_tester_provider):
    offset = chain.blocks.height + 1
    chain.mine(3)
    actual = chain.blocks.query("*", engine_to_use="__default__")
    expected = offset + 3
    assert len(actual) == expected
