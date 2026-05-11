"""
@custom:ape-fuzzer-max-examples 100
@custom:ape-stateful-step-count 50
@custom:ape-stateful-bundles a b c
"""


interface Secret:
    def add(a: uint256): nonpayable
    def sub(a: uint256, b: uint256): nonpayable
    def check(): view


@external
def initialize_bundleA() -> DynArray[uint256, 10]:
    """
    @notice
        Add some initial values to a bundle. "Initializers" are called exactly once at the
        beginning of a test (before any `rule`s are called), but could be called in any order.
        They are mostly used to initialize "Bundles" with values for the rest of the test.

    @dev
        Same as `@initializes` in Hypothesis, allowing to set up initial test state (incl Bundles).
        The return value is injected into the bundle specified by `@custom:test:stateful:targets`.
        A single return (1 value) or array return (multiple values) are supported for conveinence.

    @custom:ape-stateful-targets a
    """
    return [1, 2, 3, 5, 7, 11, 13, 17, 19, 23]


@external
def rule_add(secret: Secret, a: uint256) -> uint256:
    """
    @notice
        A rule is an action that MAY be called by the test harness as one step in the test.

        Rules can also return Bundles values, which add more choices to the associated bundle.

    @dev
        A rule is selected at random, and follows the same rules as normal tests with regard to arguments.

        If you wish to avoid calling a rule except under a particular scenario, add a precondition.

    @custom:ape-stateful-targets b
    """

    extcall secret.add(a)

    return a % 100


@external
def rule_subtract(secret: Secret, a: DynArray[uint256, 10], b: uint256):
    """
    @notice
        If a failure occurs when executing a rule, that will automatically raise a test failure.

        This may indicate a legitimate bug in what you are testing, or a design flaw in your test.

    @dev
        Each argument that has a name matching a bundle "pulls" values from the associated bundle.
        If `@custom:test:stateful:consumes` is present, then that value will instead be "consumed"
        by the rule, and therefore removed from the associated bundle (e.g. no longer available)

        To pull multiple values from a bundle, use an array (selection size is chosen at random).

    @custom:ape-stateful-consumes b
    """

    for val: uint256 in a:
        extcall secret.sub(val, b)
