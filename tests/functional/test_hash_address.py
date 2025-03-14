def test_hash_same_as_python_hash(accounts):
    for account in accounts:
        assert account.__hash__() == hash(account)


def test_address_set_membership(accounts):
    address_set = set(accounts)
    assert len(address_set) == len(accounts)
    assert accounts[0] in address_set

    new_set: set = {accounts[0], accounts[0]}
    assert len(new_set) == 1
    assert accounts[1] not in new_set


def test_address_in_dict(accounts):
    address_dict = {k: i for i, k in enumerate(accounts)}
    assert len(address_dict) == len(accounts)
    assert accounts[0] in address_dict
    assert address_dict[accounts[0]] == 0
