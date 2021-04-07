def test_use_accounts_fixture(a, accounts):
    assert a == accounts  # These are the same
    assert len(a) == len(accounts) == 10

    for a1, a2 in zip(a, accounts):
        assert a1 == a2
