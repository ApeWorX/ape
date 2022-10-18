import logging
import time

import pandas as pd
import pytest

from ape.api.query import validate_and_expand_columns
from ape.utils import BaseInterfaceModel
from ape_test.provider import CHAIN_ID


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
        "num_transactions",
        "hash",
        "number",
        "parent_hash",
        "size",
        "timestamp",
        "gas_limit",
        "gas_used",
        "base_fee",
        "difficulty",
        "total_difficulty",
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
    assert query[0].chain_id == CHAIN_ID


def test_transaction_contract_event_query(contract_instance, owner, eth_tester_provider):
    contract_instance.fooAndBar(sender=owner)
    time.sleep(0.1)
    df_events = contract_instance.FooHappened.query("*", start_block=-1)
    assert isinstance(df_events, pd.DataFrame)
    assert df_events.event_name[0] == "FooHappened"


class Model(BaseInterfaceModel):
    number: int
    timestamp: int


def test_column_expansion():
    columns = validate_and_expand_columns(["*"], Model)
    assert columns == list(Model.__fields__)


def test_column_validation(eth_tester_provider, caplog):
    with pytest.raises(ValueError) as exc_info:
        validate_and_expand_columns(["numbr"], Model)
    assert exc_info.value.args[0] == "No valid fields in ['numbr']."
    caplog.clear()

    with caplog.at_level(logging.WARNING):
        validate_and_expand_columns(["numbr", "timestamp"], Model)

    assert len(caplog.records) == 1
    assert "Unrecognized field(s) 'numbr'" in caplog.records[0].msg
    caplog.clear()

    with caplog.at_level(logging.WARNING):
        validate_and_expand_columns(["number", "timestamp", "number"], Model)

    assert len(caplog.records) == 1
    assert "Duplicate fields in ['number', 'timestamp', 'number']" in caplog.records[0].msg
    caplog.clear()
