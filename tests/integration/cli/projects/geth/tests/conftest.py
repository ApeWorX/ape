import pytest


@pytest.fixture(scope="session")
def owner(accounts):
    return accounts[0]


@pytest.fixture(scope="session")
def contract(project, owner):
    _contract = project.VyperContract.deploy(sender=owner)

    # Show that contract transactions in fixtures appear in gas report
    _contract.setNumber(999, sender=owner)

    return _contract
