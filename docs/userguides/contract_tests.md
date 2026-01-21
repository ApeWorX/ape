# Contract Tests

Ape allows you to write "contract tests", which are test cases that are actually written
in a supported smart contract language, based on which compiler plugins you have installed.
They can be particularly useful when testing complex behaviors in your smart contracts,
such as dealing with reentrancy, doing property and invariant/stateful testing, and much more.

## Test Suite Organization

In order to write a smart contract test that will execute using our ape test runner
(see [Testing](./testing.html)), you will need to add smart contract files to your test suite
that follow a specific naming convention:

```
{config.test_folder}/
  .../  # NOTE: Can have any amount of subfolders in an Ape test suite
    test*{.ext}
    # `.ext` must be registered by supported compiler in your installed plugins
```

```{important}
Tests **MUST NOT** have multiple suffixes (e.g. `.t.sol`) in them to be registered.
This is done to avoid conflicts with other testing frameworks,
such as [Foundry](https://getfoundry.sh).
```

```{note}
It is recommended (but not required) that you title your test cases as snakecased names
(e.g. `test_something.sol`).
All a test needs to be registered is a filename prefixed with `test*`,
and an extension that matches a registered compiler plugin you have installed.
```

You can have any number of other contracts in these folders as well,
such as if you need special shared logic or utilities,
but note that these will not be registered as tests by our runner,
nor will they be compiled directly when running your test suite.

## Writing Contract Tests

Using the smart contract language of your choice,
you can write test cases in your contract test file by creating **ABI-exported methods**
that start with the name `test*`, for example:

```solidity
function test_this_does_something() external {
    // Testing logic here...
}
```

You can do anything you like inside these tests, you are only limited by the language itself!
Ape simply executes all of the registered test methods it finds in your contract test files,
and then shows any errors that raise from executing them.

```{important}
Make sure that all of your test methods are "exported" into the compiled contract's ABI,
otherwise they will not register with our contract test runner, and therefore not be run.

You can have as many internal functions as you want, just know those will not register either.
```

```{note}
You are free to make use of any code provided by project dependencies,
such as [`forge-std`](https://github.com/foundry-rs/forge-std).
These can give you access to language-specific testing features others have made for you,
such as [cheatcodes](https://getfoundry.sh/forge/tests/cheatcodes).

Note that you will have to [configure any dependencies](../config.html#dependencies)
in your project's config first.
Also note that certain features (such as `forge-std`'s cheatcodes) will **only** work
on a supported node plugin (e.g. `anvil` w/ [`ape-foundry`](https://github.com/ApeWorX/ape-foundry)).

Ape's contract test feature only makes miminal assumptions on how you write your tests,
and doesn't impose a particular plugin configuration to function.
```

### Pre-test Setup

If your contract test module contains the special function `setUp`,
the test will be executed from a snapshot after deployment **that includes executing `setUp`**.
This mimics the same behavior from foundry where the initial state of a test starts after `setUp`.
However note that due to the snapshotting behavior, this feature is slightly more performant.

### Accessing Fixtures from Ape

One of Ape's best testing features (borrowed from [pytest](https://pytest.org))
is ["fixtures"](https://docs.pytest.org/en/stable/how-to/fixtures.html),
which allows the configuration of shared, test-only parameters.
You'll be delighted to find that Contract Tests in Ape get fixtures for free!

For example, let's say you have the following test fixture defined (in `tests/conftest.py`),
using the normal Ape syntax for working with your project's contracts:

```py
@pytest.fixture
def token(project, TOTAL_SUPPLY, deployer):
    return project.Token.deploy(TOTAL_SUPPLY, sender=deployer)
```

Then in your test, you can write the following to gain access to these (Python) fixture values:

```solidity
function test_token_initialization(
    IERC20 token, address deployer, uint256 TOTAL_SUPPLY
) external {
    require(token.owner() == deployer);
    require(token.totalSupply() == TOTAL_SUPPLY);
    require(token.balanceOf(deployer) == TOTAL_SUPPLY);
}
```

This can **drastically** improve the speed of writing test cases!
And since fixtures are shared among all tests and obey all the same pytest rules,
you can leverage more advanced features like [fixture scoping][fixture-scoping],
[fixture parametrization][fixture-parametrization], and more!

```{important}
Fixtures referenced in contract tests **MUST** be convertible to ABI arguments,
using Ape's conversion system. <!-- TODO: Add userguide on conversions? -->
If you reference a fixture that is **NOT** convertible to an ABI type when calling your test,
the test invocation will fail.

Whatever langauge-specific internal type that argument has in your test (e.g. contract interfaces
vs. `address`) doesn't matter to Ape when invoking it, nor does the Python type of the value matter
(e.g. `"vitalik.eth"`) either, as long as it converts to the proper ABI-exported type for the arg.
```

### Natspec Test Modifiers

Ape's contract test runner makes use of [Natspec](https://docs.soliditylang.org/en/v0.8.33/natspec-format.html)
(the "Ethereum Natural Langauge Specification" Format), and specifically "custom annotations",
in your test's contract- and function-level documentation strings in order to provide enhanced test
management features. This allows our test runner to pre-configure various settings and
[markers](https://docs.pytest.org/en/stable/how-to/mark.html) that control how your tests gets executed!

This can be really useful for specifying things like "skip this test"
(via [`xfail`](https://docs.pytest.org/en/stable/how-to/skipping.html#xfail)),
or for leveraging more advanced features of pytest like "test parametrization"
(via [`parametrize`](https://docs.pytest.org/en/stable/how-to/parametrize.html#parametrizemark)).

```{danger}
The arguments of several of these custom annotations are parsed with `eval` in order to obtain
their configured value in the testing context.

**THIS CAN ALLOW ARBITRARY CODE EXECUTION**, so avoid running Contract Tests that you didn't
**personally write or review** to ensure that you don't execute improper code.

See [the Python documentation](https://docs.python.org/3/library/functions.html#eval) for more
information about `eval` and it's potential dangers.
```

We support the following test Natspec modifiers (via custom annotations):

#### Test Result Checkers

_Used to check for specific **side effects** of running the test._

- `@custom:ape-check-reverts {expected error}`

  Check that running this test reverts with (the `eval` of) `{expected error}`.

  Example:

  ```solidity
  /// @custom:ape-check-reverts "This error gets raised"
  function test_reverts_with() external {
      revert("This error gets raised");
      // NOTE: Test succeeds **only** if it reverted with "This error gets raised"
  }
  ```

  ```{note}
  `{expected error}` **MUST** be a string literal (like in our example), hex bytesvalue,
  or it should `eval` in test context to a custom error type e.g. `my_contract.CustomError()`.
  ```

- `@custom:ape-check-emits {expected logs...}`

  Check that after the test _succeeds_, the exact set of event logs in (the `eval` of)
  `{expected logs...}` is emitted from running the test (must match **all** emitted logs).

  Example:

  ```solidity
  /// @custom:ape-check-emits
  /// - token.Approval(owner=self, spender=executor, value=100_000)
  /// - token.Approval(spender=executor, value=10_000)
  /// - token.Approval(owner=self, spender=executor)
  /// - token.Approval(owner=self, value=100)
  /// - token.Approval(value=10)
  /// - token.Approval()
  function test_emits(IERC20 token, address executor) external {
      token.approve(executor, 100000);
      token.approve(executor, 10000);
      token.approve(executor, 1000);
      token.approve(executor, 100);
      token.approve(executor, 10);
      token.approve(executor, 1);
  }
  ```

  ```{caution}
  Each case **MUST** use the `-` character prepended to the case to separate them.
  ```

  ```{note}
  Similar to Ape, we can omit arguments in the mock log objects and it will match any value.
  ```

#### Test Harness Setup

_Configures how the test should be run._

- `@custom:ape-mark-xfail <reason>`

  Run the test, but expect it to fail (and show `<reason>` as the failure reason for display).

- `@custom:ape-mark-parametrize <comma,separated,...,args> {cases...}`

  Create N cases of this test (where N is `len(cases)`),
  where each case takes a particular set of values from (the `eval` of) `{cases...}` for `*args`.

  Example:

  ```solidity
  /// @custom:ape-mark-parametrize investor,amount
  ///     - ("vitalik.eth", "100 ether")
  ///     - ("degen.eth", "10 ether")
  ///     - ("cowmilker.eth", "1 ether")
  function test_token_initialization(
      IERC20 token, address investor, uint256 amount
  ) external {
      require(token.balanceOf(investor) == amount);
  }
  ```

  ```{caution}
  Each case **MUST** use the `-` character prepended to the case to separate them.
  ```

  ```{important}
  If only one parametrized argument is used, do **NOT** enclose each parametrized case in a tuple.
  ```

  ```{note}
  This feature is similar to Foundry's "table tests" feature, but allows arbitrary python values.
  ```

#### Property Test Settings

_Configures the runner for [Property Testing](#property-testing)_

- `@custom:ape-fuzzer-max-examples {non-negative integer}`

  The maximum number of examples to generate for each Property Test.
  Must be a non-negative integer (see [Hypothesis Documentation](https://hypothesis.readthedocs.io/en/latest/reference/api.html#hypothesis.settings.max_examples) for further information).

  ```{important}
  When being used to control the maximum number of runs of a Stateful Test, this setting must be
  set **at the contract-level**, not in individual `rule` function definitions.
  ```

  ```{note}
  `max_examples` is similar to the `runs` configuration settings from Foundry.
  ```

- `@custom:ape-fuzzer-deadline {milliseconds}`

  The deadline for each example to run for (in milliseconds).
  Must be a non-negative integer (see [Hypothesis Documentation](https://hypothesis.readthedocs.io/en/latest/reference/api.html#hypothesis.settings.deadline) for further information).

#### Stateful Test Settings

_Configures the runner for [Stateful Testing](#stateful-testing)_

- `@custom:ape-stateful-step-count {non-negative integer}`

  The maximum number of `rule` calls to make in each Stateful Test example.
  Must be a non-negative integer.

  ```{important}
  This setting must be set **at the contract-level** to work,
  not in individual `rule` function definitions.
  ```

  ```{note}
  `max_examples` is similar to the `depth` configuration settings from Foundry.
  ```

- `@custom:ape-stateful-bundles <space separated bundle names>`

  The list of "Bundles" (off-chain data collections that can be pulled for stateful test arguments)
  that the test allows to use in a `rule`.

  To pull values from a Bundle in a test, simply use the name of the Bundle as the argument name:

  ```solidity
  /// @custom:ape-stateful-bundles item_id
  contract StatefulTest {
      // ...

      function rule_use_bundle_item(item_id: uint256) external {
          // Do something with `item_id`...
      }

      // NOTE: When the Bundle name is an array of items, it pulls multiple
      function rule_use_bundle_item(item_id: uint256[]) external {
          // Do something with each `item_id`...
      }

      // ...
  }
  ```

  ```{important}
  This setting must be set **at the contract-level** to work,
  not in individual `rule` function definitions.
  ```

- `@custom:ape-stateful-targets <bundle name>`

  The Bundle to add the return value(s) of the resulting `rule` or `initialize` method,
  to be accessed by subsequent `rule` invocations when the Bundle is used as an argument.

  To push values into a Bundle, do:

  ```solidity
  /// @custom:ape-stateful-bundles item_id
  contract StatefulTest {
      // NOTE: When return value is an array of items, it pushes multiple items into the bundle
      /// @custom:ape-stateful-targets item_id
      function initialize_bundle_item() external returns (uint256[2]) {
          // Adds `1` and `2` to the Bundle `item_id`, only once at start of test
          return [uint256(1), uint256(2)];
      }

      /// @custom:ape-stateful-targets item_id
      function rule_new_bundle_item() external returns (uint256) {
          // Adds `3` to the Bundle `item_id`, each time rule is called
          return 3;
      }

      // ...
  }
  ```

  ```{important}
  This setting must be set **at the function-level** (of `initialize` or `rule` functions) to work,
  not at the contract-level (where it will be ignored).
  ```

- `@custom:ape-stateful-consumes <bundle name>`

  Whether the Bundle argument should "consume" the value (e.g. remove the value from the Bundle),
  when accessed by a `rule` invocation with that Bundle as an argument.

  To consume values from a Bundle, do:

  ```solidity
  /// @custom:ape-stateful-bundles item_id
  contract StatefulTest {
      // ...

      // NOTE: The uint256 value is removed from `item_id` after executing this rule
      /// @custom:ape-stateful-targets item_id
      function rule_use_bundle_item(uint256 item_id) external {
          // ...
      }

      // ...
  }
  ```

  ```{important}
  This setting must be set **at the function-level** of `rule` functions to work,
  not at the contract-level (where it will be ignored).
  ```

### Property Testing

"Property Tests" (also known as "Fuzz Tests" in Foundry) are tests that for the most part look like
normal tests, except that there are extra argument(s) given which do not match a known fixture (or
args in the `parametrizes` modifier). The presence of these extra argument(s) turn the single test
invocation in a series of invocations (configured by the `max_examples`
[Property Test modifier](#property-test-settings)) where the value for each extra argument is
pulled at random from a "Strategy", which describes the range of all possible values that type can
have.

This adds an extra dimension to your testing, and often finds less obvious errors and bugs in your code,
so it is a good recommendation to add this to your project.
For example, say you have a "normal" contract test that looks like the following:

```solidity
function test_minting_works(
    IERC20 token, address executor
) external {
    // NOTE: `executor` is the account executing our test
    //       (by default, same as `msg.sender`)
    require(token.balanceOf(executor) == 0);

    // NOTE: The default "sender" for a mutable call is actually the test itself!
    //       (without using `vm.prank` mocking to impersonate a different account)
    token.mint(executor, 1000)
    require(token.balanceOf(executor) == 1000);
}
```

This test case demonstrates that a specific scenario works,
minting 1000 tokens to the `executor` address fixture leads to that account's balance increasing by 1000 tokens.

To rewrite this as a Property Test, we would change `executor` to a new `address` variable named `acct`
(which doesn't match a fixture in our test suite),
and then add a parameter `amt` that will randomize the amount of tokens minted to `acct`.
Our new Property Test would look like:

```
// NOTE: This modifier is not necessary to make it a Property Test, but
//       it is often useful to control the number of examples per test.
/// @custom:ape-fuzzer-max-examples 100
function test_minting_works(
    IERC20 token, address acct, uint256 amt
) external {
    require(token.balanceOf(acct) == 0);

    token.mint(acct, amt)
    require(token.balanceOf(acct) == amt);
}
```

Invoking this test might find an example where `acct` is not an allowed target for `token.mint`,
or `amt` is not an allowed amount of tokens to issue to `acct`.
This is kind of a contrived example, so it may yield pretty unexepected results,
however thanks to the power of Hypothesis and fixtures in Ape's Contract Testing feature,
we can actually **control the Strategy** of the values that we pull from (for `acct` and `amt`).

Let use a fixture to define some custom strategies in our `conftest.py` for these variable names:

```py
from eth_abi.tools import get_abi_strategy
from hypothesis import strategies as st


@pytest.fixture(scope="session")
def acct(investors):
    # NOTE: Only get addresses that are **NOT** investors
    return get_abi_strategy("address").filter(lambda a: a not in investors)


@pytest.fixture(scope="session")
def amt(TOTAL_SUPPLY):
    # NOTE: Only select values for `amt` in test case,
    #       from the range `[0, TOTAL_SUPPLY]`
    return st.integers(min_value=0, max_value=TOTAL_SUPPLY)
```

This can **drastically improve** the effectiveness of your Property Tests, as you can create
complex custom strategies that will find more relevant input scenarios more quickly!

_See [Adapting Strategies](https://hypothesis.readthedocs.io/en/latest/tutorial/adapting-strategies.html)
and [Custom Strategies](https://hypothesis.readthedocs.io/en/latest/tutorial/custom-strategies.html) from
to learn more about strategies customization._

```{important}
Defining custom fuzzer strategies is more performant than the use of `vm.assume` cheatcode.
Because strategies define **the range of valid inputs** to pull from, they don't have to "reject"
invalid inputs that you wish to skip, because they are **never generated** in the first place!
```

```{note}
Hypothesis comes out of the box with support for "coverage expansion" behavior,
similar to Foundry's "coverage-guided fuzzing" concept.
Hypothesis's backend (which is [configurable](https://hypothesis.readthedocs.io/en/latest/extensions.html#alternative-backends)
for different scenarios like longer-term testing, SMT solving, etc.) will try and maximize the "coverage" of tests
(Property or Stateful) by picking new, unique inputs every time the test is executed.

It will also pick previous examples that have been known to cause issues in the past, as well as "boundry conditions"
(values at the "boundry" of the strategy e.g. max and min value, zero, etc.) where it think it might find issues easily.
Selecting the "fuzzing domain" is best done through developing custom strategies for your tests,
and let the selection of the appropiate "value distributions" be up to Hypothesis's backend!
```

### Stateful Testing

```{important}
Any "normal" tests (functions that start with `test`) in the test module will prevent registering
the module as a Stateful Test.

The stateful test runner will **only** register a Stateful Test using the following `external` /
`public` methods with the below naming conventions (and associated state mutability):

| function prefix |      state mutability     |
| :-------------: | :-----------------------: |
|   `initialize`  |   `nonpayable` (default)  |
|      `rule`     |   `nonpayable` (default)  |
|   `invariant`   |       `view` / `pure`     |
```

Sometimes, you have tests that require testing even more complex or interdependent behavior than
Property tests allow. Stateful Testing (also known as Invariant Testing) allows the generation of
complex scenarios where a randomized sequence of calls to different "rules" (functions that start
with `rule*`), each with potentially random arguments selected to be called with, can potentially
trigger more state-dependent logic than otherwise would get triggered by a single invocation by a
Property Test case.

However, this requires a more complicated setup where a full test file is required to describe all
of the possibilities and rules for the test. For example, let's say we have a scenario where we
want to test the transfer logic of a token. We might want to explore what happens when we allow
different token holders to transfer tokens to each other. But to do that, we need a way to
introduce the concept of being a "holder" to our test, because if we just let the runner pick an
address at random (using the basic `address` Strategy) then the likelihood of selecting a holder
becomes astronomically small, leading to ineffective tests!

#### Bundles

Thankfully, Hypothesis's Stateful Test feature has the concept of "Bundles", which are buckets of
items that we can use in our Stateful Test as a strategy to select values from that matter to our
test. In this case, we want our `holder` Bundle to **only** contain addresses that **already** have
a balance. We can also use "initializers" (functions that start with `initialize*`) to pre-fill
Bundles so that our tests can start off accessing values from our Bundle which exist at the start
of the test (due to specific deployment or `setUp` logic).

Such a case might look like:

```solidity
// NOTE: Need this to access `vm` value from forge-std to use `prank` cheatcode
import {Test} from "forge-std/Test.sol";

// Creates a Bundle called `holder` to use inside the Stateful Test
/// @custom:ape-stateful-bundles holder
contract TokenTest is Test {

    // The return value(s) from this function will be added to the `holder` Bundle
    /// @custom:ape-stateful-targets holder
    function initialize_holders(
        address deployer, address[] calldata investors
    ) external returns (address[] memory) {
        address[] memory initial_holders = new address[](1 + investors.length);

        // The token `deployer` gets an initial balance on deployment, so count as a holder
        initial_holders[0] = deployer;

        // The `investors` have gotten an initial amount on deployment, so count them as holders
        for (uint i = 0; i < investors.length; i++)
            initial_holders[i + 1] = investors[i];

        // This will "pre-fill" the `holder` Bundle with `initial_holders` (to pull in other tests)
        return initial_holders;
    }

    // The return value(s) from this function will be added to the `holder` Bundle too
    /// @custom:ape-stateful-targets holder
    function rule_transfer(
        IERC20 token, address holder, address account, uint256 bips
    ) external {
        // NOTE: Get a portion of holder's balance by multiplying by our `bips` strategy
        //       (`bips` is a custom strategy, an integer that ranges from 0 to 10,000)
        uint256 amount = token.balanceOf(holder) * bips / 10000;

        // Send that holder some of our tokens
        vm.prank(holder);
        token.transfer(account, amount);

        // NOTE: Adds `account` to Bundle `holder` (unless already in it)
        return account;
    }
}
```

Notice at the top, we use the `@custom:ape-stateful-bundles` modifier to create the Bundle
`holder` that we can fill with the current token holders during the test.
Then we wrote two functions that target this bundle (via `@custom:ape-stateful-targets`):
`initialize_holders`, which pre-fills this Bundle with the holders at the time of `token`'s
deployment from our fixtures, and `rule_transfer`, which sends a varying amount of tokens from
a `holder` to another address `account`, which then gets added to our Bundle.

Thanks to the use of Bundles, we can now ensure that during our test, we only get **relevant** holders
as an input to our transfer rule, meaning we will no longer be randomly selecting 0 balance holders.
However you might notice a different problem,
which is what happens when a `holder` sends their **full balance** to `account`?
Well, unless you "consume" the value, the value remains in the Bundle for future use.
We can indicate this behavior through the use of `@custom:ape-stateful-consumes`:

```solidity
    // ...

    /// @custom:ape-stateful-consumes holder
    /// @custom:ape-stateful-targets holder
    function rule_transfer(
        IERC20 token, address holder, address account, uint256 bips
    ) external {
        // ...
    }

    // ...
```

By adding that we are "consuming" the value provided via `holder`, then each invocation of the rule
will remove the holder from the Bundle used by future invocations of the same rule.
But because we are also adding a new value to the bundle when the rule is executed,
we can keep the Bundle full of relevant values to select from for each step in the test!

#### Invariants

The last concept to understand about Stateful Testing is "invariants",
which are properties that must **always** hold during the entire execution of your test.
The default "invariant" that the runner checks for is the presence of any reverts that occur when invoking a `rule`.

But lets say you actually have additional "invariants" you want to check **after every `rule` invocation**.
We can do that by defining extra `invariant*` view functions which are called to check on the internal state.

This might look like:

```solidity
    // ...

    function invariant_check_total_supply(
        IERC20 token, uint256 TOTAL_SUPPLY
    ) view external {
        require(token.totalSupply() == TOTAL_SUPPLY);
    }

    // ...
```

For example, if during the course of operating our Stateful Test the value of `token.totalSupply()`
ever disagrees with `TOTAL_SUPPLY`, then it will show the sequnce of steps violating our invariant!

You might imagine even more complex invariants that require stateful handling inside your test.
A common technique is to use "shadow variables", which are storage variables inside your test that
maintain values useful to checking your invariants, for instance "the sum of all `balanceOf` balances".

Here's how you might employ a shadow variable in practice, first by initializing it during `setUp`,
then by checking inside one of your `invariant*` functions:

```solidity
    // ...

    uint256 balanceOf_sum;

    function setUp() {
        balanceOf_sum = 0;

        // Other setup we need to do...
    }

    // Initializers... (to set `holder` Bundle like above)

    /// @custom:ape-stateful-targets holder
    function rule_mint(
        MyToken token, address account, uint256 amount
    ) external returns (address) {
        token.mint(account, amount);

        // NOTE: Keep track of newly minted balance in shadow variable
        balanceOf_sum += amount;

        // NOTE: Add `account` to `holder` Bundle.
        return account;
    }

    // Other rules... (`transfer`/`transferFrom` use, `burn`, etc.)

    function invariant_total_supply(MyToken token) view external {
        require(token.totalSupply() == balanceOf_sum);
    }

    // Other invariants...
```

_Stateful Testing is a complex subject, and it may benefit you to review the [Hypothesis Documentation](https://hypothesis.readthedocs.io/en/latest/stateful.html)._

```{note}
Due to their complex and multi-transaction flows, Stateful Tests can take longer to execute than
normal contract tests or even Property Tests.

It is recommended to initially start by setting a small value for [`step_count`](#stateful-testing)
and [`max_examples`](#property-testing) while developing your test, and then only increasing those
limits once you like how the test is working (e.g. it runs without any intermittent failures).
```

## Running Contract Tests

You can run contract tests alongside normal Python-based tests with the same Ape test runner,
and make use of all the same test discovery feature flags supported by `ape test`.
(see [`ape test` command userguide](./testing.html#ape-testing-commands))

The big difference with contract tests is that they are only compiled **when the test is run**,
so if there is a compilation error it will only raise during `ape test` (and not `ape compile`).

[fixture-parametrization]: https://docs.pytest.org/en/stable/how-to/fixtures.html#parametrizing-fixtures
[fixture-scoping]: https://docs.pytest.org/en/stable/how-to/fixtures.html#scope-sharing-fixtures-across-classes-modules-packages-or-session
