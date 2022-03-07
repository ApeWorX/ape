from ape import accounts, chain


def test_basic_query(test_provider):
    a = accounts.test_accounts[0]
    a.transfer(a, 100)
    a.transfer(a, 100)
    a.transfer(a, 100)
    df = chain.blocks.query("number")
    assert len(df) == 3
    assert df["number"][0] == 0
    df = chain.blocks.query("number", "timestamp")
    assert len(df) == 3
    assert df["timestamp"][2] > df["timestamp"][1] > df["timestamp"][0]
