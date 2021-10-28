def test_one_interface(accounts, project):
    test_account = accounts[0]
    assert test_account
    contract_type = project.Interface
    assert contract_type
