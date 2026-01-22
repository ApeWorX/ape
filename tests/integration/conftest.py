# NOTE: Fixtures for use with both Solidity and Vyper "Contract Tests" feature
import pytest


@pytest.fixture(scope="session")
def openzeppelin(project):
    dep = project.dependencies["openzeppelin"]
    return dep[max(dep)]


@pytest.fixture()
def token(openzeppelin, accounts):
    return openzeppelin.ERC20Mock.deploy(sender=accounts[-1])
