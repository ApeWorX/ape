import time

import narwhals as nw
import pytest
from ethpm_types.abi import MethodABI

from ape.api import query as query_api
from ape.api.query import (
    BlockQuery,
    ContractMethodQuery,
    to_dataframe,
    validate_and_expand_columns,
)
from ape.exceptions import QueryEngineError
from ape.utils import DEFAULT_TEST_CHAIN_ID, BaseInterfaceModel


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


def test_transaction_contract_event_query_starts_query_at_deploy_tx(
    contract_instance, owner, eth_tester_provider
):
    contract_instance.fooAndBar(sender=owner)
    time.sleep(0.1)
    df_events = contract_instance.FooHappened.query("*")
    assert isinstance(df_events, nw.DataFrame)
    assert df_events["event_name"][0] == "FooHappened"


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


def test_specify_engine(chain, eth_tester_provider):
    offset = chain.blocks.height + 1
    chain.mine(3)
    actual = chain.blocks.query("*", engine_to_use="__default__")
    expected = offset + 3
    assert len(actual) == expected
