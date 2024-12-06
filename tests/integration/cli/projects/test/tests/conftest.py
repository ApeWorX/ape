import pytest


@pytest.fixture(scope="session")
def session_one(chain):
    chain.mine(4)


@pytest.fixture(scope="session")
def session_two(chain):
    chain.mine(2)
