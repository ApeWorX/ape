import pytest

INITIAL_BALANCE = 1_000_1 * 10**18


@pytest.fixture(scope="function")
def function_one(chain):
    chain.mine(1)


@pytest.fixture(scope="module", autouse=True)
def module_one(chain):
    chain.mine(3)


@pytest.fixture(scope="session")
def alice(accounts):
    yield accounts[0]


@pytest.fixture(scope="session")
def bob(accounts):
    yield accounts[1]


@pytest.fixture(params=(5, 6, 7))
def parametrized_mining(chain, request):
    chain.mine(request.param)
    return request.param


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


def test_noop():
    # This forces auto-use fixtures to fire off before
    # any requested fixtures, for testing purposes.
    assert True


class TestClass:
    @pytest.fixture(scope="class", autouse=True)
    def classminer(self, chain):
        chain.mine(9)

    def test_chain(self, chain):
        """
        Sessions haven't run yet.
        Module mined 3 + 1 = 4 total.
        Class mined 9.
        4 + 9 = 13
        """
        assert chain.blocks.height == 13


def test_isolation_first(alice, bob, chain, start_block_number):
    assert chain.provider.get_block("latest").number == start_block_number
    assert bob.balance == INITIAL_BALANCE
    alice.transfer(bob, "1 ether")


def test_isolation_second(bob, chain, start_block_number):
    assert chain.provider.get_block("latest").number == start_block_number
    assert bob.balance == INITIAL_BALANCE


def test_isolation_with_session_module_and_function(chain, session_one, session_two, function_one):
    """
    The sessions should be used, so that is 6.
    Function is 1 and the module 3.
    Also, setup does a transfer - that bumps up another 1.
    Expected is 11.
    """
    # NOTE: Module is on autouse=True
    assert chain.blocks.height == 11


def test_isolation_module_ran_after(chain):
    """
    This test runs after the test above.
    We should be back at the beginning of the state after
    the session and module function but before the function.
    Expected = sessions + module = 4 + 2 + 3 + 1 (from setup) = 10
    """
    assert chain.blocks.height == 10


def test_parametrized_fixtures(start_block_number, chain, parametrized_mining):
    assert chain.blocks.height == start_block_number + parametrized_mining


@pytest.fixture(scope="session", params=(5, 6, 7))
def parametrized_transaction(request, alice, bob):
    """
    2 more get added to the session here!
    """
    return alice.transfer(bob, f"{request.param} wei")


def test_use_parametrized_transaction(parametrized_transaction):
    """
    The real test is in the next file `test_iso_session.py`.
    The session fixtures should know about these and add an additional
    `3` to the `6` to make `9.`
    """
    _ = parametrized_transaction
    assert True  # Testing isolation after the fixture runs.
