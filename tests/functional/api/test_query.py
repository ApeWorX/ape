from ape import chain


def test_basic_query(eth_tester_provider):
    chain.mine(3)
    assert chain.blocks.query("number").to_dict() == {"number": {0: 0, 1: 1, 2: 2}}
    df = chain.blocks.query("number", "timestamp")
    assert len(df) == 3
    assert df["timestamp"][2] >= df["timestamp"][1] >= df["timestamp"][0]
