import pytest
from pydantic import ValidationError

from ape import chain
from ape.api.query import AccountTransactionQuery, BlockQuery, BlockTransactionQuery


def test_basic_query(eth_tester_provider):
    chain.mine(3)
    assert chain.blocks.query("number").to_dict() == {"number": {0: 0, 1: 1, 2: 2, 3: 3}}
    df = chain.blocks.query("number", "timestamp")
    assert len(df) == 4
    assert df["timestamp"][3] > df["timestamp"][2] >= df["timestamp"][1] >= df["timestamp"][0]
    df_all = chain.blocks.query("*")
    columns = list(df_all.columns)
    assert columns == [
        "gas_data",
        "consensus_data",
        "num_transactions",
        "hash",
        "number",
        "parent_hash",
        "size",
        "timestamp",
    ]


def test_block_transaction_query():
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
