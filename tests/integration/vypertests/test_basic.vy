# pragma version ~=0.4.3


@external
def test_it_works():
    assert 1 + 1 == 2, "We can do tests in vyper!"


@external
def test_using_fixtures(accounts: DynArray[address, 10], executor: address):
    """
    @notice
        Test cases can use args to access Python fixtures from your Ape test suite.
        Ape looks up the fixture by arg name and then provides that to call the method.

    @dev
        The fixtures MUST be valid ABI types, or convertible using Ape's conversion system.

        Valid Ape types include:
        - `AccountAPI` types (converts to `address`)
        - `ContractInstance` types (converts to `address` or interface types)
        - strings that Ape's conversion system supports
          e.g. `"vitalik.eth"`, `"WETH"`, `"500 USDC"`, etc.
    """
    # NOTE: `accounts` is actually an Ape fixture!
    for a: address in accounts:
        assert a.balance >= 10 ** 18

    # NOTE: the `executor` fixture is actually the caller of the test
    assert executor == msg.sender
    # NOTE: the `executor` fixture is in the `accounts` fixture
    assert executor in accounts
