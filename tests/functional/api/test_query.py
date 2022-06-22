import pytest
from pydantic import ValidationError

from ape import chain
from ape.api.query import AccountTransactionQuery, BlockQuery, BlockTransactionQuery


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


def test_block_transaction_query_api():
    query = BlockTransactionQuery(columns=["*"], block_id=0)
    assert query.columns == [
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


def test_block_transaction_query(eth_tester_provider, sender, receiver):
    sender.transfer(receiver, 100)
    query = chain.blocks[-1].transactions
    assert len(query) == 1
    assert query[0].value == 100
    assert query[0].chain_id == 61


def test_block_query(eth_tester_provider):
    chain.mine(3)
    with pytest.raises(ValidationError) as err:
        BlockQuery(columns=["numbr"], start_block=0, stop_block=2)
    assert "Unrecognized field 'numbr'" in str(err.value)
    with pytest.raises(ValidationError) as err:
        BlockQuery(columns=["number", "timestamp", "number"], start_block=0, stop_block=2)
    assert "Duplicate fields in ['number', 'timestamp', 'number']" in str(err.value)


def test_account_query(eth_tester_provider):
    chain.mine(3)
    query_kwargs = dict(
        account="0x0000000000000000000000000000000000000000", start_nonce=0, stop_nonce=2
    )
    with pytest.raises(ValidationError) as err:
        AccountTransactionQuery(columns=["none"], **query_kwargs)
    assert "Unrecognized field 'none'" in str(err.value)
    with pytest.raises(ValidationError) as err:
        AccountTransactionQuery(columns=["nonce", "chain_id", "nonce"], **query_kwargs)
    assert "Duplicate fields in ['nonce', 'chain_id', 'nonce']" in str(err.value)
