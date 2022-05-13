import pytest


@pytest.fixture(scope="session")
def alice(accounts):
    yield accounts[0]


@pytest.fixture(scope="session")
def bob(accounts):
    yield accounts[1]


@pytest.fixture(scope="module", autouse=True)
def setup(alice, bob, chain):
    assert chain.provider.get_block("latest").number == 0
    alice.transfer(bob, 10**18)
    assert chain.provider.get_block("latest").number == 1


def test_isolation_first(alice, bob, chain):
    assert chain.provider.get_block("latest").number == 1
    assert bob.balance == 1_000_001 * 10**18
    alice.transfer(bob, "1 ether")


def test_isolation_second(bob, chain):
    assert chain.provider.get_block("latest").number == 1
    assert bob.balance == 1_000_001 * 10**18
