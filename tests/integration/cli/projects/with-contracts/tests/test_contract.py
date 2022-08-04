import pytest


@pytest.fixture(scope="module")
def owner(accounts):
    return accounts[0]


@pytest.fixture(scope="module")
def contract_from_fixture(project, owner):
    return owner.deploy(project.Contract)


def test_contract_interaction_in_tests(project, contract_from_fixture, owner):
    contract_in_test = owner.deploy(project.Contract)
    contract_in_test.setNumber(123, sender=owner)
    actual = contract_in_test.myNumber()
    assert actual == 123

    contract_from_fixture.setNumber(456, sender=owner)
    actual = contract_from_fixture.myNumber()
    assert actual == 456
