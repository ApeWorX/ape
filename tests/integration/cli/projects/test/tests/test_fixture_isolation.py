import pytest

INITIAL_BALANCE = 1_000_1 * 10**18


@pytest.fixture(scope="session")
def alice(accounts):
    yield accounts[0]


@pytest.fixture(scope="session")
def bob(accounts):
    yield accounts[1]


@pytest.fixture(scope="module", autouse=True)
def setup(alice, bob, chain):
    start_number = chain.provider.get_block("latest").number
    alice.transfer(bob, 10**18)
    actual = chain.provider.get_block("latest").number
    expected = start_number + 1
    assert actual == expected


@pytest.fixture(scope="module")
def start_block_number(chain):
    return chain.blocks.height


def test_isolation_first(alice, bob, chain, start_block_number):
    assert chain.provider.get_block("latest").number == start_block_number
    assert bob.balance == INITIAL_BALANCE
    alice.transfer(bob, "1 ether")


def test_isolation_second(bob, chain, start_block_number):
    assert chain.provider.get_block("latest").number == start_block_number
    assert bob.balance == INITIAL_BALANCE
