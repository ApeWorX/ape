def test_contract_interaction_in_tests(project, contract_from_fixture, owner):
    contract_in_test = owner.deploy(project.ContractA)
    contract_in_test.setNumber(333, sender=owner)
    actual = contract_in_test.myNumber()
    assert actual == 333

    contract_from_fixture.setNumber(456, sender=owner)
    actual = contract_from_fixture.myNumber()
    assert actual == 456


def test_fail_txn_err_handling(project, contract_from_fixture, owner):
    contract_in_test = owner.deploy(project.ContractA)

    # Errors (uncaught)
    contract_in_test.setNumber(5, sender=owner)
