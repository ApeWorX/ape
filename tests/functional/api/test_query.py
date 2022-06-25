import pytest

from ape import chain
from ape.api.query import validate_and_expand_columns


def test_basic_query(eth_tester_provider):
    chain.mine(3)
    df1 = chain.blocks.query("*")
    assert list(df1["number"].values) == [0, 1, 2, 3]
    df2 = chain.blocks.query("number", "timestamp")
    assert len(df2) == 4
    assert (
        df2.iloc[3]["timestamp"]
        >= df2.iloc[2]["timestamp"]
        >= df2.iloc[1]["timestamp"]
        >= df2.iloc[0]["timestamp"]
    )
    assert list(df1.columns) == [
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


def test_relative_block_query(eth_tester_provider):
    chain.mine(10)
    df = chain.blocks.query("*", start_block=-8, stop_block=-2)
    assert len(df) == 7
    assert df.number.min() == chain.blocks[-8].number == 3
    assert df.number.max() == chain.blocks[-2].number == 9


def test_block_transaction_query(eth_tester_provider, sender, receiver):
    sender.transfer(receiver, 100)
    query = chain.blocks[-1].transactions
    assert len(query) == 1
    assert query[0].value == 100
    assert query[0].chain_id == 61


def test_column_expansion():
    all_fields = [
        "chain_id",
        "receiver",
        "sender",
        "gas_limit",
        "nonce",
        "value",
        "data",
        "type",
        "max_fee",
        "max_priority_fee",
        "required_confirmations",
        "signature",
    ]
    columns = validate_and_expand_columns(["*"], all_fields)
    assert columns == all_fields


def test_column_validation(eth_tester_provider):
    all_fields = ["number", "timestamp"]
    with pytest.raises(ValueError) as err:
        validate_and_expand_columns(["numbr"], all_fields)
    assert "Unrecognized field 'numbr'" in str(err.value)
    with pytest.raises(ValueError) as err:
        validate_and_expand_columns(["number", "timestamp", "number"], all_fields)
    assert "Duplicate fields in ['number', 'timestamp', 'number']" in str(err.value)
