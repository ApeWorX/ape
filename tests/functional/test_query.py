import time

import pandas as pd
import pytest

from ape.api.query import validate_and_expand_columns
from ape.utils import DEFAULT_TEST_CHAIN_ID, BaseInterfaceModel


def test_basic_query(chain, eth_tester_provider):
    chain.mine(3)
    blocks_df0 = chain.blocks.query("*")
    blocks_df1 = chain.blocks.query("number", "timestamp")

    assert list(blocks_df0["number"].values)[:4] == [0, 1, 2, 3]
    assert len(blocks_df1) == len(chain.blocks)
    assert (
        blocks_df1.iloc[3]["timestamp"]
        >= blocks_df1.iloc[2]["timestamp"]
        >= blocks_df1.iloc[1]["timestamp"]
        >= blocks_df1.iloc[0]["timestamp"]
    )
    assert list(blocks_df0.columns) == [
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
    assert df.number.min() == chain.blocks[-8].number == start_block + 3
    assert df.number.max() == chain.blocks[-2].number == start_block + 9


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
    assert isinstance(df_events, pd.DataFrame)
    assert df_events.event_name[0] == "FooHappened"


def test_transaction_contract_event_query_starts_query_at_deploy_tx(
    contract_instance, owner, eth_tester_provider
):
    contract_instance.fooAndBar(sender=owner)
    time.sleep(0.1)
    df_events = contract_instance.FooHappened.query("*")
    assert isinstance(df_events, pd.DataFrame)
    assert df_events.event_name[0] == "FooHappened"


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


def test_specify_engine(chain, eth_tester_provider):
    offset = chain.blocks.height + 1
    chain.mine(3)
    actual = chain.blocks.query("*", engine_to_use="__default__")
    expected = offset + 3
    assert len(actual) == expected
