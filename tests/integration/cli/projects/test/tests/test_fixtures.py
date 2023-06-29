from ape.managers.accounts import TestAccountManager
from ape.managers.chain import ChainManager
from ape.managers.networks import NetworkManager
from ape.managers.project import ProjectManager

# Even though it is set on the class, it needs to be set _in the test_
# for some reason.
TestAccountManager.__test__ = False


def test_accounts(accounts):
    assert isinstance(accounts, TestAccountManager)


def test_chain(chain):
    assert isinstance(chain, ChainManager)


def test_contract(chain, Contract):
    assert Contract == chain.contracts.instance_at


def test_networks(networks):
    assert isinstance(networks, NetworkManager)


def test_project(project):
    assert isinstance(project, ProjectManager)


def test_built_in_fixtures(chain, capsys):
    _ = chain  # Include chain to show we can use with our shipped filters
    assert True
