import pytest


@pytest.fixture(scope="module")
def owner(accounts):
    return accounts[0]


@pytest.fixture(scope="module")
def contract_from_fixture(project, owner):
    return owner.deploy(project.ContractA)
