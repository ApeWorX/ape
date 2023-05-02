from ape.contracts import ContractInstance
from ape.managers.accounts import TestAccountManager
from ape.managers.chain import ChainManager, ContractInstance
from ape.managers.networks import NetworkManager
from ape.managers.project import ProjectManager


def test_accounts(accounts):
    assert isinstance(accounts, TestAccountManager)


def test_chain(chain):
    assert isinstance(chain, ChainManager)


def test_deploy(owner, contract_container, chain, clean_contracts_cache):
    contract = owner.deploy(contract_container, 0)

def test_contract(accounts, contract_container):
    contract = accounts.test_accounts[0].deploy(contract_container, sender=accounts.test_accounts[0])
    assert isinstance(contract, ContractInstance)
    assert contract.address


def test_networks(networks):
    assert isinstance(networks, NetworkManager)


def test_project(project):
    assert isinstance(project, ProjectManager)


def test_built_in_fixtures(chain, capsys):
    _ = chain  # Include chain to show we can use with our shipped filters
    assert True
