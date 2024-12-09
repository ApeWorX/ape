import pytest

import ape

INITIAL_BALANCE = 1_000_1 * 10**18


@pytest.fixture(scope="function")
def function_one(chain):
    chain.mine(1)


TOKEN_MAP = {
    "WETH": "weth-token",
    "DAI": "dai-token",
    "BAT": "bat-token",
}


@ape.fixture(scope="module", chain_isolation=False, params=("WETH", "DAI", "BAT"))
def token_key(request):
    return TOKEN_MAP[request.param]


def test_token_key(token_key):
    # TODO: Improve this test - show token key doesn't trigger
    #   resets in those unfortunate conditions.
    assert True


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


@pytest.fixture(scope="session", params=(1, 2, 3))
def parametrized_transaction(request, alice, bob):
    """
    3 more get added to the session here!
    """
    alice.transfer(bob, f"{request.param} wei")
    return request.param


@pytest.fixture(scope="session", params=(1, 2, 3))
def second_parametrized_transaction(request, alice, bob):
    """
    2 more get added to the session here!
    """
    alice.transfer(bob, f"{request.param * 2} wei")
    return request.param


@pytest.fixture
def functional_fixture_using_session(chain, session_one):
    """
    Showing the transactions in a functional-scoped
    fixture that use a session-scoped fixture don't
    persist on-chain.
    """
    _ = session_one
    chain.mine()
    return 11  # expected: 10 built up plus this 1.


# Parametrized to show it works more than once.
@pytest.mark.parametrize("it", (0, 1, 2))
def test_functional_fixture_using_session(chain, functional_fixture_using_session, it):
    assert chain.blocks.height == functional_fixture_using_session


def test_use_parametrized_transaction(chain, parametrized_transaction):
    starting = 10  # All session + module
    assert chain.blocks.height == starting + parametrized_transaction


def test_use_parametrized_transaction_again(chain, parametrized_transaction):
    """
    Should not have invalidated parametrized fixture.
    """
    starting = 10  # All session + module
    assert chain.blocks.height == starting + parametrized_transaction


@pytest.fixture
def functional_fixture_using_parametrized_session(chain, parametrized_transaction):
    chain.mine()
    return 11 + parametrized_transaction


def test_functional_fixture_using_parametrized_session(
    chain, functional_fixture_using_parametrized_session
):
    assert chain.blocks.height == functional_fixture_using_parametrized_session


@pytest.mark.parametrize("foo", (1, 2, 3))
def test_parametrized_test(foo):
    """
    Ensuring parametrized tests don't mess up our isolation-fixture logic
    (it was the case at one point!)
    """
    assert isinstance(foo, int)


def test_use_isolate_in_test(chain, parametrized_transaction):
    """
    Show the isolation we control doesn't affect
    the isolation fixtures.
    """
    _ = parametrized_transaction  # Using this for complexity.
    start_block = chain.blocks.height
    with chain.isolate():
        chain.mine()
        assert chain.blocks.height == start_block + 1

    assert chain.blocks.height == start_block
