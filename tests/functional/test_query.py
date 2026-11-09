import json
import time
from types import SimpleNamespace
from typing import Any, cast

import narwhals.stable.v2 as nw
import pytest
from eth_utils import to_hex
from ethpm_types.abi import EventABI, MethodABI
from pydantic import Field

from ape.api import query as query_api
from ape.api.query import (
    BlockQuery,
    ContractEventQuery,
    ContractMethodQuery,
    CursorAPI,
    to_dataframe,
    validate_and_expand_columns,
)
from ape.exceptions import QueryEngineError
from ape.managers.query import QueryManager, QueryResult
from ape.types import ContractLog
from ape.utils import DEFAULT_TEST_CHAIN_ID, BaseInterfaceModel
from ape_cache import query as cache_query
from ape_cache.query import BlockCursor, CacheQueryProvider, _canonical_height
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


def test_contract_event_query_step(contract_instance, owner, chain, eth_tester_provider):
    # Emit one event per block across a contiguous window, then sample every other block.
    start = chain.blocks.height + 1
    for _ in range(4):
        contract_instance.fooAndBar(sender=owner)

    stop = chain.blocks.height
    df = contract_instance.FooHappened.query(
        "block_number", start_block=start, stop_block=stop, step=2
    )
    assert [int(number) for number in df["block_number"].to_list()] == list(
        range(start, stop + 1, 2)
    )


def test_account_history_query(sender, receiver, eth_tester_provider):
    receipt = sender.transfer(receiver, 100)
    # The next nonce is len(history). The transfer itself is receipt.nonce.
    df = sender.history.query("nonce", "value", stop_nonce=receipt.nonce)
    assert isinstance(df, nw.DataFrame)
    assert [int(value) for value in df["nonce"].to_list()] == [int(receipt.nonce)]
    assert [int(value) for value in df["value"].to_list()] == [100]


def test_account_history_wildcard_flattens_the_transaction(sender, receiver, eth_tester_provider):
    receipt = sender.transfer(receiver, 100)
    df = sender.history.query("*", start_nonce=receipt.nonce, stop_nonce=receipt.nonce)
    assert "transaction" not in df.columns
    assert {"nonce", "value", "sender", "receiver", "txn_hash", "gas_used"} <= set(df.columns)
    assert [int(value) for value in df["nonce"].to_list()] == [int(receipt.nonce)]
    assert [int(value) for value in df["value"].to_list()] == [100]
    assert df["sender"].to_list() == [sender.address]
    assert df["receiver"].to_list() == [receiver.address]


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


def test_query_detects_backend_after_a_missing_parent_package(monkeypatch):
    def find_spec(name):
        if name == "modin.pandas":
            # What ``find_spec`` does for a submodule whose parent is not installed.
            raise ModuleNotFoundError("No module named 'modin'")

        return object() if name == "cudf" else None

    monkeypatch.setattr(query_api, "find_spec", find_spec)
    query_api._detected_dataframe_backend.cache_clear()
    try:
        assert query_api._detected_dataframe_backend() is nw.Implementation.CUDF
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


def test_solver_keeps_a_rigid_cursor_for_its_whole_window_across_boundaries():
    # The partial cursor adds a boundary inside the rigid cursor. The rigid cursor
    # cannot be cut there, but its whole window still covers the query.
    pieces = _solve(
        _Window(0, 10),
        [_Cursor(0, 10, cost=1, shrinkable=False), _Cursor(0, 4, cost=5)],
    )
    assert [(piece.query.start_index, piece.query.end_index) for piece in pieces] == [(0, 10)]


def test_solver_picks_a_cheaper_cut_over_a_rigid_whole_window():
    pieces = _solve(
        _Window(0, 10),
        [
            _Cursor(0, 10, cost=5, shrinkable=False),
            _Cursor(0, 10, cost=1),
            _Cursor(0, 4, cost=5),
        ],
    )
    assert [(piece.query.start_index, piece.query.end_index) for piece in pieces] == [(0, 10)]
    assert pieces[0].time_per_row == 1


def test_solver_accepts_a_sole_rigid_cursor_on_a_stepped_query():
    # 0 through 9 with step 2 samples 0, 2, 4, 6 and 8. The cursor's window ends at 9,
    # past the last sample, but it still covers every requested index.
    query = _Window(0, 9, step=2)
    pieces = _solve(query, [_Cursor(0, 9, cost=1, step=2, shrinkable=False)])
    assert [(piece.query.start_index, piece.query.end_index) for piece in pieces] == [(0, 9)]
    assert _coverage(query, pieces).query is query


def test_solver_accepts_a_sole_rigid_block_cursor_on_a_stepped_block_query():
    class RigidBlockCursor(_ListCursor):
        def shrink(self, start_index=None, end_index=None):
            if (start_index, end_index) != (self.query.start_index, self.query.end_index):
                raise NotImplementedError

            return self

    query = BlockQuery(columns=["number"], start_block=0, stop_block=9, step=2)
    cursor = RigidBlockCursor(query=query, items=[])
    assert _solve(query, [cursor]) == [cursor]


def test_solver_cannot_cut_a_rigid_cursor_wider_than_the_query():
    with pytest.raises(QueryEngineError, match=r"missing coverage in window \[2:8\]"):
        _solve(_Window(2, 8), [_Cursor(0, 10, cost=1, shrinkable=False)])


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


def test_solver_ends_a_stepped_query_at_its_last_sampled_index():
    # 0 through 9 with step 2 samples 0, 2, 4, 6 and 8.
    query = _Window(0, 9, step=2)
    cached = [_Cursor(index, index, cost=0.01, step=2) for index in range(0, 10, 2)]
    pieces = _solve(query, [_Cursor(0, 9, cost=1, step=2), *cached])
    assert [(piece.query.start_index, piece.query.end_index) for piece in pieces] == [
        (index, index) for index in range(0, 10, 2)
    ]
    assert _coverage(query, pieces).query is query

    # Cold, a single cursor covers the window and ends past the last sample.
    assert _coverage(query, [_Cursor(0, 9, cost=1, step=2)]).query is query


def test_solver_checks_only_active_cursors_on_a_warm_stepped_query(monkeypatch):
    from ape.managers import query as query_manager

    calls = 0
    covers = query_manager._cursor_covers

    def counting_covers(cursor, start, end):
        nonlocal calls
        calls += 1
        return covers(cursor, start, end)

    monkeypatch.setattr(query_manager, "_cursor_covers", counting_covers)
    samples = 10_000
    query = _Window(0, 2 * samples - 1, step=2)
    cached = [_Cursor(index, index, cost=0.01, step=2) for index in range(0, 2 * samples, 2)]
    pieces = _solve(query, [_Cursor(0, 2 * samples - 1, cost=1, step=2), *cached])

    assert len(pieces) == samples
    # The wide cursor and one cached cursor per segment, not every cursor per segment.
    assert calls <= 2 * samples


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


def test_columns_come_from_the_most_derived_ecosystem_block(monkeypatch):
    # A chain such as Sonic extends Ethereum's block with its own field.
    class ChainBlock(Block):
        timestamp_nano: int = 0

    package = ChainBlock.__module__.split(".", 1)[0]
    monkeypatch.setattr(query_api, "_ecosystem_packages", lambda: [package, "ape_ethereum"])

    assert query_api._concrete_model(query_api.BlockAPI) is ChainBlock
    query = BlockQuery(columns=["timestamp_nano"], start_block=0, stop_block=0)
    assert query.columns == ["timestamp_nano"]
    assert "timestamp_nano" in BlockQuery(columns=["*"], start_block=0, stop_block=0).columns


class _ListCursor(CursorAPI):
    items: list[Any]

    @property
    def time_per_row(self) -> float:
        return 0.0

    def as_model_iter(self):
        yield from self.items


def _log(block_number: int = 1, **event_arguments) -> ContractLog:
    return ContractLog(
        event_name="Thing",
        event_arguments=event_arguments,
        transaction_hash="0x" + "00" * 32,
        block_number=block_number,
        block_hash="0x" + "00" * 32,
        log_index=0,
    )


def _event_query(*inputs: tuple[str, str], columns=("*",)) -> ContractEventQuery:
    event = EventABI.model_validate(
        {
            "type": "event",
            "name": "Thing",
            "inputs": [{"name": name, "type": type_, "indexed": False} for name, type_ in inputs],
        }
    )
    return ContractEventQuery(
        columns=list(columns),
        contract="0x" + "00" * 20,
        event=event,
        start_block=1,
        stop_block=2,
    )


def test_event_argument_column_reads_the_decoded_value():
    # ``get`` is also a method on ``ContractLog``. The column is the event input.
    query = _event_query(("get", "uint256"), columns=("get", "block_number"))
    cursor = _ListCursor(query=query, items=[_log(get=42)])
    frame = cursor.as_dataframe(nw.Implementation.POLARS)
    assert frame["get"].to_list() == [42]
    assert frame["block_number"].to_list() == [1]


@pytest.mark.parametrize("backend", ("polars", "pandas"))
def test_event_frame_keeps_full_width_integers(backend):
    max_uint = 2**256 - 1
    query = _event_query(
        ("value", "uint256"), ("values", "uint256[]"), columns=("value", "values", "block_number")
    )
    cursor = _ListCursor(
        query=query, items=[_log(value=max_uint, values=[max_uint, 1]), _log(value=1, values=[])]
    )
    frame = cursor.as_dataframe(nw.Implementation.from_backend(backend))
    assert frame["value"].to_list() == [max_uint, 1]
    assert [list(values) for values in frame["values"].to_list()] == [[max_uint, 1], []]
    # Columns that fit keep the library's own integer type.
    assert frame.schema["block_number"] == nw.Int64

    wildcard = _ListCursor(
        query=_event_query(("value", "uint256")), items=[_log(value=max_uint)]
    ).as_dataframe(nw.Implementation.from_backend(backend))
    assert wildcard["value"].to_list() == [max_uint]
    assert wildcard["event_arguments"].to_list() == [{"value": max_uint}]


@pytest.mark.parametrize("backend", ("polars", "pandas"))
def test_event_frame_keeps_wide_integers_numeric(backend):
    ten_ether = 10 * 10**18  # Wider than a signed 64-bit integer.
    query = _event_query(("value", "uint256"), columns=("value", "block_number"))
    cursor = _ListCursor(
        query=query,
        items=[_log(value=ten_ether), _log(value=ten_ether), _log(value=1)],
    )
    frame = cursor.as_dataframe(nw.Implementation.from_backend(backend))
    assert frame["value"].to_list() == [ten_ether, ten_ether, 1]
    assert frame["value"].sum() == 2 * ten_ether + 1
    assert frame.filter(nw.col("value") > 10**18)["value"].to_list() == [ten_ether, ten_ether]
    if backend == "polars":
        assert frame.schema["value"] == nw.Int128


def test_frame_keeps_python_ints_wider_than_128_bits():
    frame = query_api._from_columns({"value": [2**200, None]}, nw.Implementation.POLARS)
    assert frame.schema["value"] == nw.Object
    assert frame["value"].to_list() == [2**200, None]

    unsigned = query_api._from_columns({"value": [2**127, 1]}, nw.Implementation.POLARS)
    assert unsigned.schema["value"] == nw.UInt128
    assert unsigned["value"].to_list() == [2**127, 1]


@pytest.mark.parametrize("values", ([10 * 10**18], [2**127], [-1], [2**200]))
def test_wide_integer_windows_stack_with_narrow_windows(values, eth_tester_provider):
    query = _event_query(("value", "int256"), columns=("value", "block_number"))
    narrow = _FrameCursor(
        query=query.model_copy(update={"stop_block": 1}), items=[_log(block_number=1, value=1)]
    )
    wide = _FrameCursor(
        query=query.model_copy(update={"start_block": 2}),
        items=[_log(block_number=2, value=value) for value in values],
    )
    result: QueryResult = QueryResult(query=query, cursors=[narrow, wide])
    frame = result.as_dataframe(backend="polars")
    assert frame["value"].to_list() == [1, *values]


class _FrameCursor(_ListCursor):
    # A plugin cursor that builds its own frame.
    def as_dataframe(self, backend):
        return query_api._from_columns(
            query_api._column_values(self.query.columns, self.as_model_iter()), backend
        )


@pytest.mark.parametrize("cursor_class", (_ListCursor, _FrameCursor))
def test_partial_frames_with_an_empty_window_stack(cursor_class, eth_tester_provider):
    query = _event_query(("value", "uint256"), columns=("value", "block_number"))
    first = cursor_class(query=query.model_copy(update={"stop_block": 1}), items=[])
    second = cursor_class(
        query=query.model_copy(update={"start_block": 2}), items=[_log(block_number=2, value=5)]
    )
    result: QueryResult = QueryResult(query=query, cursors=[first, second])

    frame = result.as_dataframe(backend="polars")
    assert frame["value"].to_list() == [5]
    assert frame["block_number"].to_list() == [2]


class _NativeFrameCursor(_ListCursor):
    # A plugin cursor that hands back a frame it built with its own types.
    native: Any

    def as_dataframe(self, backend):
        return nw.from_native(self.native)


def _plugin_frame(kind: str):
    import pandas as pd
    import polars as pl

    if kind == "int32":
        return pl.DataFrame({"number": pl.Series([2, 3], dtype=pl.Int32), "gas_used": [5, 6]})
    elif kind == "uint64":
        return pl.DataFrame({"number": pl.Series([2, 3], dtype=pl.UInt64), "gas_used": [5, 6]})
    elif kind == "column_order":
        return pl.DataFrame({"gas_used": [5, 6], "number": [2, 3]})
    elif kind == "lazy":
        return pl.LazyFrame({"number": [2, 3], "gas_used": [5, 6]})
    elif kind == "string":
        return pl.DataFrame({"number": [2, 3], "gas_used": ["5", "6"]})
    elif kind == "pandas":
        return pd.DataFrame({"number": [2, 3], "gas_used": [5, 6]})

    raise ValueError(kind)


@pytest.mark.parametrize("kind", ("int32", "uint64", "column_order", "lazy", "pandas"))
def test_plugin_and_rpc_frames_stack(kind, eth_tester_provider):
    query = BlockQuery(columns=["number", "gas_used"], start_block=0, stop_block=3)
    rpc = _ListCursor(
        query=query.model_copy(update={"stop_block": 1}),
        items=[_header(0, gasUsed=3), _header(1, gasUsed=4)],
    )
    plugin = _NativeFrameCursor(
        query=query.model_copy(update={"start_block": 2}), items=[], native=_plugin_frame(kind)
    )
    result: QueryResult = QueryResult(query=query, cursors=[rpc, plugin])

    frame = result.as_dataframe(backend="polars")
    assert frame.implementation is nw.Implementation.POLARS
    assert frame.columns == ["number", "gas_used"]
    assert frame["number"].to_list() == [0, 1, 2, 3]
    assert frame["gas_used"].to_list() == [3, 4, 5, 6]
    assert frame.schema["gas_used"].is_integer()
    assert frame["gas_used"].sum() == 18


def test_plugin_and_rpc_frames_with_incompatible_types(eth_tester_provider):
    query = BlockQuery(columns=["number", "gas_used"], start_block=0, stop_block=3)
    rpc = _ListCursor(
        query=query.model_copy(update={"stop_block": 1}),
        items=[_header(0, gasUsed=3), _header(1, gasUsed=4)],
    )
    plugin = _NativeFrameCursor(
        query=query.model_copy(update={"start_block": 2}), items=[], native=_plugin_frame("string")
    )
    result: QueryResult = QueryResult(query=query, cursors=[rpc, plugin])
    with pytest.raises(QueryEngineError, match="incompatible types for column 'gas_used'"):
        result.as_dataframe(backend="polars")


def test_partial_block_frames_with_empty_and_populated_uncles(eth_tester_provider):
    def block(number, uncles):
        return Block.model_validate(
            {
                "gasLimit": 1,
                "gasUsed": 0,
                "hash": "0x" + f"{number:064x}",
                "number": number,
                "parentHash": "0x" + "00" * 32,
                "timestamp": number,
                "num_transactions": 0,
                "uncles": uncles,
            }
        )

    query = BlockQuery(columns=["number", "uncles"], start_block=0, stop_block=1)
    result: QueryResult = QueryResult(
        query=query,
        cursors=[
            _ListCursor(query=query.model_copy(update={"stop_block": 0}), items=[block(0, [])]),
            _ListCursor(
                query=query.model_copy(update={"start_block": 1}),
                items=[block(1, ["0x" + "22" * 32])],
            ),
        ],
    )

    frame = result.as_dataframe(backend="polars")
    assert frame["number"].to_list() == [0, 1]
    assert [len(uncles) for uncles in frame["uncles"].to_list()] == [0, 1]


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


def _header(number: int, **fields) -> Block:
    return Block.model_validate(
        {
            "gasLimit": 1,
            "gasUsed": 0,
            "hash": "0x" + f"{number + 1:064x}",
            "number": number,
            "parentHash": "0x" + "00" * 32,
            "timestamp": number,
            "num_transactions": 0,
            "size": 1,
            **fields,
        }
    )


class _CountingBlockCursor(_ListCursor):
    reads: list[int] = Field(default_factory=list)

    def shrink(self, start_index=None, end_index=None):
        return self

    def as_model_iter(self):
        for block in self.items:
            self.reads.append(block.number)
            yield block


def _cached_result(tmp_path, monkeypatch, blocks, canonical_height=1_000_000):
    # Act like a public network, with settled history up to ``canonical_height``.
    monkeypatch.setattr(CacheQueryProvider, "chain_cache_folder", lambda self: tmp_path)
    monkeypatch.setattr(CacheQueryProvider, "uses_cache", True)
    monkeypatch.setattr(cache_query, "_canonical_height", lambda provider: canonical_height)
    query = BlockQuery(
        columns=["number"], start_block=blocks[0].number, stop_block=blocks[-1].number
    )
    cursor = _CountingBlockCursor(query=query, items=blocks)
    result: QueryResult = QueryResult(query=query, cursors=[cursor])
    CacheQueryProvider().cache(result)
    return result, cursor, tmp_path / "blocks" / ".number"


def test_block_cache_does_not_fetch_transactions(tmp_path, monkeypatch, eth_tester_provider):
    block = _header(7, num_transactions=4, size=1)
    result, _, index = _cached_result(tmp_path, monkeypatch, [block])
    assert list(result.as_model_iter()) == [block]

    payload = json.loads((index / "7").read_text())
    assert "transactions" not in payload
    assert payload["number"] == 7
    assert payload["num_transactions"] == 4


def test_write_block_leaves_no_tempfile(tmp_path, eth_tester_provider):
    cache_query._write_block(tmp_path, _header(3))
    assert json.loads((tmp_path / "3").read_text())["number"] == 3
    assert list(tmp_path.glob(".*")) == []

    # An existing file is left alone, so a partial rename never clobbers it.
    (tmp_path / "3").write_text("keep")
    cache_query._write_block(tmp_path, _header(3))
    assert (tmp_path / "3").read_text() == "keep"


def test_block_cache_stores_blocks_as_they_are_read(tmp_path, monkeypatch, eth_tester_provider):
    blocks = [_header(number) for number in range(2, 6)]
    result, cursor, index = _cached_result(tmp_path, monkeypatch, blocks)
    # Planning and the cache hook fetch nothing.
    assert cursor.reads == []

    rows = result.as_model_iter()
    assert next(rows).number == 2
    assert cursor.reads == [2]
    assert sorted(int(path.name) for path in index.iterdir()) == [2]

    assert [block.number for block in rows] == [3, 4, 5]
    assert cursor.reads == [2, 3, 4, 5]
    assert sorted(int(path.name) for path in index.iterdir()) == [2, 3, 4, 5]


def test_block_cache_skips_blocks_that_can_still_reorganize(
    tmp_path, monkeypatch, eth_tester_provider
):
    blocks = [_header(number) for number in range(2, 6)]
    result, _, index = _cached_result(tmp_path, monkeypatch, blocks, canonical_height=3)
    assert [block.number for block in result.as_model_iter()] == [2, 3, 4, 5]
    assert sorted(int(path.name) for path in index.iterdir()) == [2, 3]


def _provider(finalized=None, latest=None, required_confirmations=0):
    def get_block(block_id):
        number = {"finalized": finalized, "latest": latest}[block_id]
        if isinstance(number, Exception):
            raise number

        return SimpleNamespace(number=number)

    network = SimpleNamespace(required_confirmations=required_confirmations)
    return cast(Any, SimpleNamespace(get_block=get_block, network=network))


def test_canonical_height_is_the_finalized_block():
    provider = _provider(finalized=5, latest=10, required_confirmations=2)
    assert cache_query._canonical_height(provider) == 5


@pytest.mark.parametrize("finalized", (ValueError("finalized not supported"), None))
def test_canonical_height_without_finality_uses_confirmations(finalized):
    provider = _provider(finalized=finalized, latest=10, required_confirmations=2)
    assert cache_query._canonical_height(provider) == 8


@pytest.mark.parametrize("finalized", (ValueError("finalized not supported"), None))
def test_canonical_height_without_finality_or_confirmations_settles_nothing(finalized):
    # The head is not settled, so it must not be cached and later served after a reorg.
    provider = _provider(finalized=finalized, latest=10, required_confirmations=0)
    assert cache_query._canonical_height(provider) == -1

    provider = _provider(finalized=finalized, latest=ValueError("down"), required_confirmations=2)
    assert cache_query._canonical_height(provider) == -1


def test_block_cache_skips_unsettled_blocks_when_finality_fails(
    tmp_path, monkeypatch, eth_tester_provider
):
    blocks = [_header(number) for number in range(2, 6)]
    result, _, index = _cached_result(tmp_path, monkeypatch, blocks)
    provider = _provider(finalized=ValueError("finalized not supported"), latest=5)
    monkeypatch.setattr(cache_query, "_canonical_height", lambda _: _canonical_height(provider))
    assert [block.number for block in result.as_model_iter()] == [2, 3, 4, 5]
    assert not index.exists() or list(index.iterdir()) == []


def test_block_cache_is_off_for_a_local_chain(chain, eth_tester_provider, tmp_path, monkeypatch):
    # A snapshot restore and a new block at the same height must not serve the old block.
    monkeypatch.setattr(CacheQueryProvider, "cache_folder", lambda self, *args, **kwargs: tmp_path)
    monkeypatch.setattr(CacheQueryProvider, "chain_cache_folder", lambda self: tmp_path)
    engine = chain.query_manager.engines["cache"]
    assert not engine.uses_cache

    # Snapshot IDs are block hashes. Mine first, so this snapshot is not the test
    # isolation's own snapshot. Restoring it would drop that one, and the chain
    # would stay advanced for later tests (such as block serialization).
    chain.mine()
    snapshot = chain.snapshot()
    chain.mine()
    height = chain.blocks.height
    first = chain.blocks.query("hash", start_block=height, stop_block=height)["hash"].to_list()
    chain.restore(snapshot)
    chain.mine(timestamp=chain.pending_timestamp + 100)
    second = chain.blocks.query("hash", start_block=height, stop_block=height)["hash"].to_list()

    assert first != second
    assert second == [chain.blocks[height].hash]
    assert not (tmp_path / "blocks").exists()
    query = BlockQuery(columns=["number"], start_block=0, stop_block=height)
    assert list(engine.execute(query)) == []


def test_block_cache_is_kept_per_chain(tmp_path, monkeypatch, eth_tester_provider, mocker):
    # Two custom networks with the same name, but different chains, share a network folder.
    monkeypatch.setattr(CacheQueryProvider, "cache_folder", lambda self, *args, **kwargs: tmp_path)
    monkeypatch.setattr(CacheQueryProvider, "uses_cache", True)
    monkeypatch.setattr(CacheQueryProvider, "_genesis_hashes", {})
    monkeypatch.setattr(cache_query, "_canonical_height", lambda provider: 1_000_000)
    provider_class = type(eth_tester_provider)
    chain_id = mocker.patch.object(provider_class, "chain_id", new_callable=mocker.PropertyMock)
    genesis = {1111: _header(0, hash="0x" + "aa" * 32), 2222: _header(0, hash="0x" + "bb" * 32)}
    mocker.patch.object(
        provider_class, "get_block", side_effect=lambda block_id: genesis[chain_id.return_value]
    )
    engine = CacheQueryProvider()
    query = BlockQuery(columns=["hash"], start_block=0, stop_block=0)

    def cached_hashes():
        return [
            to_hex(block.hash)
            for cursor in engine.execute(query)
            for block in cursor.as_model_iter()
        ]

    def read_through(block):
        cursor = _CountingBlockCursor(query=query, items=[block])
        result: QueryResult = QueryResult(query=query, cursors=[cursor])
        engine.cache(result)
        return list(result.as_model_iter())

    chain_id.return_value = 1111
    read_through(genesis[1111])
    assert cached_hashes() == ["0x" + "aa" * 32]

    # Another chain on the same network name does not see the first chain's blocks.
    chain_id.return_value = 2222
    assert cached_hashes() == []
    read_through(genesis[2222])
    assert cached_hashes() == ["0x" + "bb" * 32]

    chain_id.return_value = 1111
    assert cached_hashes() == ["0x" + "aa" * 32]
    assert engine.chain_cache_folder() == tmp_path / "1111" / ("aa" * 32)

    # The same chain ID with another genesis block is another chain too.
    monkeypatch.setattr(CacheQueryProvider, "_genesis_hashes", {})
    genesis[1111] = _header(0, hash="0x" + "cc" * 32)
    assert cached_hashes() == []


def test_block_cache_is_off_when_the_chain_is_unknown(tmp_path, monkeypatch, eth_tester_provider):
    monkeypatch.setattr(CacheQueryProvider, "cache_folder", lambda self, *args, **kwargs: tmp_path)
    monkeypatch.setattr(CacheQueryProvider, "uses_cache", True)
    monkeypatch.setattr(CacheQueryProvider, "_genesis_hashes", {})

    def no_genesis(*args, **kwargs):
        raise ValueError("no genesis")

    monkeypatch.setattr(type(eth_tester_provider), "get_block", no_genesis)
    engine = CacheQueryProvider()
    query = BlockQuery(columns=["hash"], start_block=0, stop_block=0)
    assert engine.chain_cache_folder() is None
    assert list(engine.execute(query)) == []
    cursor = _CountingBlockCursor(query=query, items=[_header(0)])
    result: QueryResult = QueryResult(query=query, cursors=[cursor])
    engine.cache(result)
    assert result.cursors == [cursor]


def test_block_cache_local_chain_test_leaves_the_chain_as_it_found_it(chain):
    # Runs after ``test_block_cache_is_off_for_a_local_chain``. Its snapshot restore
    # must not leave blocks behind for the tests that follow.
    assert chain.blocks.height == 0


def test_find_ranges_keeps_cached_runs(tmp_path):
    index = tmp_path / ".number"
    index.mkdir()
    for number in (1, 2, 3, 5):
        (index / str(number)).write_text("{}")

    assert list(CacheQueryProvider.find_ranges(index, start=0, end=10)) == [(1, 3), (5, 5)]
    assert list(CacheQueryProvider.find_ranges(index, start=0, end=0)) == []


def test_find_ranges_joins_runs_on_the_step_grid(tmp_path):
    index = tmp_path / ".number"
    index.mkdir()
    for number in (0, 1, 2, 4, 5, 8):
        (index / str(number)).write_text("{}")

    assert list(CacheQueryProvider.find_ranges(index, start=0, end=9, step=2)) == [(0, 4), (8, 8)]
    assert list(CacheQueryProvider.find_ranges(index, start=1, end=9, step=2)) == [(1, 1), (5, 5)]


def test_cache_cursor_total_time_counts_stepped_rows(tmp_path, eth_tester_provider):
    # Inclusive span with step 2 samples five rows (0, 2, 4, 6, 8), not nine.
    query = BlockQuery(columns=["number"], start_block=0, stop_block=9, step=2)
    cursor = BlockCursor(query=query, cache_folder=tmp_path)
    assert cursor.total_time == pytest.approx(5 * cursor.time_per_row)

    # A single-block cursor costs one row, not zero.
    single = BlockQuery(columns=["number"], start_block=5, stop_block=5)
    assert BlockCursor(query=single, cache_folder=tmp_path).total_time == pytest.approx(
        cursor.time_per_row
    )


def test_specify_engine(chain, eth_tester_provider):
    offset = chain.blocks.height + 1
    chain.mine(3)
    actual = chain.blocks.query("*", engine_to_use="__default__")
    expected = offset + 3
    assert len(actual) == expected


def test_planning_warns_when_a_plugin_raises(chain, eth_tester_provider, ape_caplog, monkeypatch):
    class BrokenEngine:
        def execute(self, query):
            raise RuntimeError("boom")

        def cache(self, result):
            return None

    engines = {**chain.query_manager.engines, "broken": BrokenEngine()}
    monkeypatch.setattr(chain.query_manager, "engines", engines, raising=False)

    # The default engine still covers the query; the broken plugin is skipped.
    df = chain.blocks.query("number", start_block=0, stop_block=0)
    assert [int(number) for number in df["number"].to_list()] == [0]
    assert any("Skipping BrokenEngine while planning" in message for message in ape_caplog.messages)


def test_otterscan_creation_cursor_is_empty_for_a_null_result(eth_tester_provider, mocker):
    from ape.api.query import ContractCreationQuery
    from ape_node.query import ContractCreationCursor

    make_request = mocker.patch.object(type(eth_tester_provider), "make_request", return_value=None)
    query = ContractCreationQuery(columns=["*"], contract="0x" + "00" * 20)

    assert list(ContractCreationCursor(query=query).as_model_iter()) == []
    make_request.assert_called_once_with("ots_getContractCreator", [query.contract])


def test_account_cursor_stops_at_its_stop_nonce(eth_tester_provider, mocker):
    from ape.api.query import AccountTransactionQuery
    from ape.managers.query import _RpcAccountTransactionCursor

    # Nonces 0 and 1 were mined in the same block, so a search for nonce 0 sees both.
    receipts = [SimpleNamespace(nonce=0), SimpleNamespace(nonce=1)]
    mocker.patch.object(
        type(eth_tester_provider),
        "get_transactions_by_account_nonce",
        side_effect=lambda account, start, stop: iter(receipts),
    )
    account = "0x" + "11" * 20

    def nonces(start, stop):
        query = AccountTransactionQuery(
            columns=["nonce"], account=account, start_nonce=start, stop_nonce=stop
        )
        return [
            receipt.nonce for receipt in _RpcAccountTransactionCursor(query=query).as_model_iter()
        ]

    assert nonces(0, 0) + nonces(1, 1) == [0, 1]
