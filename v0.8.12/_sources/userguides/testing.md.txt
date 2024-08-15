# Testing

Testing an ape project is important and easy.

## Pytest

Before learning how testing works in Ape, you should have an understanding of [the pytest framework](https://docs.pytest.org/en/7.4.x/) and its concepts such as fixtures, mark-decorators, and pytest plugins such as x-dist, pytest-mock, and pytest-cov.
Once you have learned about pytest, Ape testing becomes intuitive because it is built on top of pytest.
In fact, `ape-test` is itself a `pytest` plugin!

You write your smart-contracts much like you write regular Python tests.

## Test Structure

Tests must be located in a project's `tests/` directory. Each **test file** must start with `test_` and have the `.py` extension, such as `test_my_contract.py`.
Each **test method** within the file must also start with `test_`.
The following is an example test:

```python
def test_add():
    assert 1 + 1 == 2
```

```{note}
`pytest` assumes the *actual* value is on the left and the *expected* value is on the right.
```

## Test Pattern

Tests are generally divisible into three parts:

1. Set-up
2. Invocation
3. Assertion

An example of the setup-phase would be creating a `pytest.fixture` that deploys our smart contract.
(To learn more about pytest fixtures in Ape, see the `Fixtures` section below!)
For now, what you need to know is that it's a piece of code that executes before the test runs, and it is decorated with a `@pytest.fixture`.

The second phase is `Invocation`, which encompasses invoking the function we are testing.
The last phase, `Assertion`, requires enacting on the expectation about how the code should behave.
Let's assume there is an `authorized_method()` that requires the owner of the contract to make the transaction.
If the sender of the transaction is not the owner, the transaction will fail to complete and will revert.
We use `assert` statements in Ape (and `pytest`) to check that our expectations are correct.
A test passes if all the `assert` statements are `True` and it fails if any are `False`.

This is an example of how that test may look:

```python
import ape
import pytest

# SETUP PHASE
# NOTE: More on fixtures is discussed in later sections of this guide!
@pytest.fixture
def owner(accounts):
    return accounts[0]

@pytest.fixture
def my_contract(owner, project):
    return owner.deploy(project.MyContract)

def test_authorization(my_contract, owner, not_owner):
    # INVOCATION PHASE
    my_contract.set_owner(sender=owner)
    assert owner == my_contract.owner()

    # ASSERTION PHASE
    with ape.reverts("!authorized"):
        my_contract.authorized_method(sender=not_owner)
```

```{note}
Ape has built-in test and fixture isolation for all pytest scopes.
To disable isolation add the `--disable-isolation` flag when running `ape test`
```

## Fixtures

Now that we have discussed the full flow of a test, let's dive deeper into the specific parts, starting with `pytest.fixtures`.

You can define and use `pytest` fixtures in your Ape tests.
Learn more about fixtures from [this guide](https://docs.pytest.org/en/7.1.x/explanation/fixtures.html).
The syntax and functionalities of fixtures work exactly the same in Ape as it does with `pytest`.

The `ape-test` plugin comes with fixtures you will likely want to use.
The following guide explains each fixture that comes with Ape.

### accounts fixture

You have access to test accounts.
These accounts are automatically funded, and you can use them to transact in your tests.
Access each [test account](../methoddocs/api.html?highlight=testaccount#ape.api.accounts.TestAccountAPI) by index from the `accounts` fixture:

```python
def test_my_method(accounts):
    owner = accounts[0]
    receiver = accounts[1]
```

For code readability and sustainability, create your own fixtures using the `accounts` fixture:

```python
import pytest

@pytest.fixture
def owner(accounts):
    return accounts[0]


@pytest.fixture
def receiver(accounts):
    return accounts[1]


def test_my_method(owner, receiver):
    ...
```

You can configure your accounts by changing the `mnemonic`, `number_of_accounts`, and `balance` in the `test` section of your `ape-config.yaml` file:

```yaml
test:
  mnemonic: test test test test test test test test test test test junk
  number_of_accounts: 5
  balance: 100_000 ETH
```

If you are running tests against `anvil`, your generated test accounts may not correspond to the `anvil`'s default generated accounts despite using the same mnemonic. In such a case, you are able to specify a custom derivation path in `ape-config.yaml`:

```yaml
test:
  mnemonic: test test test test test test test test test test test junk
  number_of_accounts: 5
  hd_path: "m/44'/60'/0'/0/{}"
```

If you are using a provider that supports impersonating accounts, such as [Foundry](https://github.com/ApeWorX/ape-foundry), use the address as the key in the test-accounts manager:

```python
@pytest.fixture
def vitalik(accounts):
    return accounts["0xab5801a7d398351b8be11c439e05c5b3259aec9b"]
```

You can also call `accounts.impersonate_account()` for improved readability and performance.

```python
@pytest.fixture
def vitalik(accounts):
    return accounts.impersonate_account("0xab5801a7d398351b8be11c439e05c5b3259aec9b")
```

Using a fork-provider such as [Hardhat](https://github.com/ApeWorX/ape-hardhat), when using a contract instance as the sender in a transaction, it will be automatically impersonated:

```python
def test_my_method(project, accounts):
    contract = project.MyContract.deploy(sender=accounts[0])
    other_contract = project.OtherContract.deploy(sender=accounts[0])
    contract.my_method(sender=other_contract)
```

It has the same interface as the [TestAccountManager](../methoddocs/managers.html#ape.managers.accounts.TestAccountManager), (same as doing `accounts.test_accounts` in a script or the console).

### chain fixture

Use the chain fixture to access the connected provider or adjust blockchain settings.

For example, increase the pending timestamp:

```python
def test_in_future(chain):
    chain.pending_timestamp += 86000
    assert "Something"
    chain.pending_timestamp += 86000
    assert "Something else"
```

It has the same interface as the [ChainManager](../methoddocs/managers.html#ape.managers.chain.ChainManager).

### networks fixture

Use the `networks` fixture to change the active provider in tests.

```python
def test_multi_chain(networks):
    assert "Something"  # Make assertion in root network

    # NOTE: Assume have ecosystem named "foo" with network "local" and provider "bar"
    with networks.foo.local.use_provider("bar"):
        assert "Something else"
```

It has the same interface as the [NetworkManager](../methoddocs/managers.html#ape.managers.networks.NetworkManager).

### project fixture

You also have access to the `project` you are testing. You will need this to deploy your contracts in your tests.

```python
import pytest


@pytest.fixture
def owner(accounts):
    return accounts[0]


@pytest.fixture
def my_contract(project, owner):
    #           ^ use the 'project' fixture from the 'ape-test' plugin
    return owner.deploy(project.MyContract)
```

It has the same interface as the [ProjectManager](../methoddocs/managers.html#module-ape.managers.project.manager).

### Contract fixture

Use the `Contract` fixture to create contract instances:

```python
@pytest.fixture
def my_contract(Contract):
    return Contract(<address>)
```

It has the same interface as the [ChainManager](../methoddocs/managers.html#ape.managers.chain.ChainManager).

## Ape testing commands

```bash
ape test
```

To run a particular test:

```bash
ape test test_my_contract
```

Use ape test `-I` to open the interactive mode at the point of exception. This allows the user to inspect the point of failure in your tests.

```bash
ape test test_my_contract -I -s
```

## Test Providers

Out-of-the-box, your tests run using the `eth-tester` provider, which comes bundled with ape.
If you have Ethereum node software installed, you can use the `ape-node` plugin that also comes with ape.

```bash
ape test --network ethereum:local:node
```

Each testing plugin should work the same way. You will have access to the same test accounts.

Another option for testing providers is the [ape-hardhat](https://github.com/ApeWorX/ape-hardhat) plugin, which does not come with `ape` but can be installed by including it in the `plugins` list in your `ape-config.yaml` file or manually installing it using the command:

```bash
ape plugins install hardhat
```

### Mining

Test providers allow you to control mining.
For example, mine an empty block using the [mine](../methoddocs/api.html#ape.api.providers.TestProviderAPI.mine) method:

```python
from ape import chain

chain.provider.mine()
```

You can also pass it a number of blocks to mine:

```python
from ape import chain

chain.provider.mine(5)
```

By default, testing providers automatically mine after sending transactions.
However, you can disable this feature by setting the property.

```python
from ape import chain

chain.provider.auto_mine = False
# You can also re-enable
chain.provider.auto_mine = True
```

## Advanced Testing Tips

If you want to use sample projects, follow this link to [Ape Academy](https://github.com/ApeAcademy).

```
project                     # The root project directory
└── tests/                  # Project tests folder, ran using the 'ape test' command to run all tests within the folder.
    └── conftest.py         # A file to define global variable for testing
    └── test_accounts.py    # A test file, if you want to ONLY run one test file you can use 'ape test test_accounts.py' command
    └── test_mint.py        # A test file
```

Here is an example of a test function from a sample [NFT project](https://github.com/ApeAcademy/ERC721)

```python
def test_account_balance(project, owner, receiver, nft):
    quantity = 1
    nft.mint(receiver, quantity, ["0"], value=nft.PRICE() * quantity, sender=owner)
    actual = project.balanceOf(receiver)
    expect = quantity
    assert actual == expect
```

## Testing Transaction Reverts

Similar to `pytest.raises()`, you can use `ape.reverts()` to assert that contract transactions fail and revert.
To learn more about reverts in Ape, see the [reverts guide](./reverts.html).

From our earlier example we can see this in action:

```python
import ape

def test_authorization(my_contract, owner, not_owner):
    my_contract.set_owner(sender=owner)
    assert owner == my_contract.owner()

    with ape.reverts("!authorized"):
        my_contract.authorized_method(sender=not_owner)
```

`reverts()` takes two optional parameters:

### `expected_message`

This is the expected revert reason given when the transaction fails.
If the message in the `ContractLogicError` raised by the transaction failure is empty or does not match the `expected_message`, then `ape.reverts()` will raise an `AssertionError`.

You may also supply an `re.Pattern` object to assert on a message pattern, rather than on an exact match.

```python
import ape
import re

# Matches explicitly "foo" or "bar"
with ape.reverts(re.compile(r"^(foo|bar)$")):
    ...
```

### `dev_message`

This is the expected dev message corresponding to the line in the contract's source code where the error occurred.
These can be helpful in optimizing for gas usage and keeping revert reason strings shorter.

Dev messages take the form of a comment in Vyper, and should be placed on the line that may cause a transaction revert:

```python
assert x != 0  # dev: invalid value
```

Take for example:

```python
# @version 0.3.7

@external
def check_value(_value: uint256) -> bool:
    assert _value != 0  # dev: invalid value
    return True
```

We can explicitly cause a transaction revert and check the failed line by supplying an expected `dev_message`:

```python
import ape

def test_authorization(my_contract, owner):
    with ape.reverts(dev_message="dev: invalid value"):
        my_contract.check_value(sender=owner)
```

When the transaction reverts and `ContractLogicError` is raised, `ape.reverts()` will check the source contract to see if the failed line contains a message.

There are a few scenarios where `AssertionError` will be raised when using `dev_message`:

- If the line in the source contract has a different dev message or no dev message
- If the contract source cannot be obtained
- If the transaction trace cannot be obtained

Because `dev_message` relies on transaction tracing to function, you must use a provider like [ape-hardhat](https://github.com/ApeWorX/ape-hardhat) when testing with `dev_message`.

You may also supply an `re.Pattern` object to assert on a dev message pattern, rather than on an exact match.

```python
import ape

# Matches explictly "dev: foo" or "dev: bar"
with ape.reverts(dev_message=re.compile(r"^dev: (foo|bar)$")):
    ...
```

### Caveats

#### Language Support

As of `ape` version `0.5.6`, `dev_messages` assertions are available for contracts compiled with [ape-vyper](https://github.com/ApeWorX/ape-vyper), but not for those compiled with [ape-solidity](https://github.com/ApeWorX/ape-solidity) or [ape-cairo](https://github.com/ApeWorX/ape-cairo).

#### Inlining

Due to function inlining, the position of the `# dev: ...` message may sometimes be one line higher than expected:

```python
@external
def foo(_x: decimal) -> decimal:  # dev: correct location
    return sqrt(_x)  # dev: incorrect location
```

This typically only applies when trying to add dev messages to statements containing built-in function calls.

#### Non-reentrant Functions

Similarly, if you require dev assertions for non-reentrant functions you must be sure to leave the comment on the function that should not have reentry:

```python
@internal
@nonreentrant('lock')
def _foo_internal():  # dev: correct location
    pass

@external
@nonreentrant('lock')
def foo():
    self._foo_internal()  # dev: incorrect location
```

### Custom Errors

In your tests, you can make assertions about custom errors raised.
(For more information on custom errors, [see reverts guide on custom errors](./reverts.html#custom-errors).)

For example, assume a custom exception in a Solidity contract (variable `contract`) is called `Unauthorized`.
It can be accessed via `contract.Unauthorized`.
We can ensure unauthorized withdraws are disallowed by writing the following test:

```python
import ape
import pytest

@pytest.fixture
def owner(accounts):
    return accounts[0]

@pytest.fixture
def hacker(accounts):
    return accounts[1]

@pytest.fixture
def contract(owner, project):
    return owner.deploy(project.MyContract)

def test_unauthorized_withdraw(contract, hacker):
    with ape.reverts(contract.Unauthorized, unauth_address=hacker.address):
        contract.withdraw(sender=hacker)
```

You can also use custom error types from the contract container (from `ape.project` or the `project` fixture):

```python
import ape

def test_unauthorized(contract, hacker, project):
    with ape.reverts(project.MyContract.Unauthorized, unauth_address=hacker.address):
        contract.withdraw(sender=hacker)
```

You may need to use the container approach for asserting on custom errors that occur during failing `deploy` transactions because you won't have access to the contract instance yet.
Here is an example of what that may look like:

```python
import ape

def test_error_on_deploy(account, project):
    with ape.reverts(project.Token.MyCustomError):
        ape.project.HasError.deploy(sender=account)
```

Alternatively, you can attempt to use the address from the revert error to find the error type.

```{note}
The address will only exist for transactions that were published (e.g. not for failures during estimating gas), and this may only work on certain providers.
```

```python
import ape

def test_error_on_deploy(account):
    # NOTE: We are using `as rev` here to capture the revert info
    # so we can attempt to lookup the contract later.
    with ape.reverts() as rev:
        ape.project.HasError.deploy(sender=account)
    
    assert rev.value.address is not None, "Receipt never found, contract never cached"
    
    # Grab the cached instance using the error's address
    # and assert the custom error this way.
    contract = ape.Contract(rev.value.address)
    assert isinstance(rev.value, contract.MyError)
```

## Multi-chain Testing

The Ape framework supports connecting to alternative networks / providers in tests.

To run an entire test using a specific network / provider combination, use the `use_network` pytest marker:

```python
import pytest

@pytest.mark.use_network("fantom:local:test")
def test_my_fantom_test(chain):
    assert chain.provider.network.ecosystem.name == "fantom"

@pytest.mark.use_network("ethereum:local:test")
def test_my_ethereum_test(chain):
    assert chain.provider.network.ecosystem.name == "ethereum"
```

To switch networks mid-test, use the `networks` context-manager:

```python
# Switch to Fantom mid test
def test_my_multichain_test(networks):
    # The test starts in 1 ecosystem but switches to another
    assert networks.provider.network.ecosystem.name == "ethereum"

    with networks.fantom.local.use_provider("test") as provider:
        assert provider.network.ecosystem.name == "fantom"

    # You can also use the context manager like this:
    with networks.parse_network_choice("fantom:local:test") as provider:
       assert provider.network.ecosystem.name == "fantom"
```

You can also set the network context in a pytest fixture.
This is useful if certain fixtures must run in certain networks.

```python
import pytest

@pytest.fixture
def stark_contract(networks, project):
    with networks.parse_network_choice("starknet:local"):
        yield project.MyStarknetContract.deploy()

def test_starknet_thing(stark_contract, stark_account):
    # Uses the starknet connection via the stark_contract fixture
    receipt = stark_contract.my_method(sender=stark_account)
    assert not receipt.failed
```

When you exit a provider's context, Ape **does not** disconnect the provider.
When you re-enter that provider's context, Ape uses the previously-connected provider.
At the end of the tests, Ape disconnects all the providers.
Thus, you can enter and exit a provider's context as much as you need in tests.

## Gas Reporting

To include a gas report at the end of your tests, you can use the `--gas` flag.

```{note}
This feature works best when using a provider with tracing support, such as [ape-foundry](https://github.com/ApeWorX/ape-foundry).
When not using a provider with adequate tracing support, such as `EthTester`, gas reporting is limited to receipt-level data.
```

```bash
ape test --network ethereum:local:foundry --gas
```

At the end of test suite, you will see tables such as:

```sh
                            FundMe Gas

  Method           Times called    Min.    Max.    Mean   Median
 ────────────────────────────────────────────────────────────────
  fund                        8   57198   91398   82848    91398
  withdraw                    2   28307   38679   33493    33493
  changeOnStatus              2   23827   45739   34783    34783
  getSecret                   1   24564   24564   24564    24564

                     TestContract Gas

  Method      Times called    Min.    Max.    Mean   Median
 ───────────────────────────────────────────────────────────
  setNumber              1   51021   51021   51021    51021
```

The following demonstrates how to use the `ape-config.yaml` file to exclude contracts and / or methods from the gas report:

```yaml
test:
  gas:
    exclude:
      - method_name: DEBUG_*         # Exclude all methods starting with `DEBUG_`.
      - contract_name: MockToken     # Exclude all methods in contract named `MockToken`.
      - contract_name: PoolContract  # Exclude methods starting with `reset_` in `PoolContract`.
        method_name: reset_*
```

Similarly, you can exclude sources via the CLI option `--gas-exclude`.
The value `--gas-exclude` takes is a comma-separated list of colon-separated values representing the structure similar as above, except you must explicitly use `*` where meaning "all".
For example to exclude all methods starting with `DEBUG_`, you would do:

```bash
ape test --gas --gas-exclude "*:DEBUG_*".
```

To exclude all methods in the `MockToken` contract, do:

```bash
ape test --gas --gas-exclude MockToken
```

And finally, to exclude all methods starting with `reset_` in `PoolContract`, do:

```bash
ape test --gas --gas-exclude "PoolContract:reset_*"
```

## Iterative Testing

Ape has a set of flags that controls running your test suite locally in a "watch" mode,
which means watching for updates to files in your project and re-triggering the test suite.

To enable this mode, run `ape test --watch` to set up this mode using the default settings.
While in this mode, any time a `.py` file (i.e. your tests) or smart contract source file
(i.e. any files that get compiled using your installed compiler plugins) is added, removed,
or changed, then the `ape test` task will be re-triggered, based on a polling interval.

To exit this mode, press Ctrl+D (on Linux or macOS) to stop the execution and undo it.

## Contract Coverage

To get contract coverage, use the `--coverage` flag when running `ape test`:

```shell
ape test --coverage
```

```{note}
Some types of coverage require using a provider that supports transaction tracing, such as `ape-hardhat` or `ape-foundry`.
```

Without using a provider with adequate tracing support, coverage is limited to receipt-level data.

Afterwards, you should see a coverage report looking something like:

```shell
============================================= Coverage Profile =============================================
               Contract Coverage               
                                               
  Name          Stmts   Miss   Cover    Funcs  
 ───────────────────────────────────────────── 
  Contract.vy   7       1      85.71%   80.0% 
```

To generate other coverage reports such as XML or HTML, configure it like so:

```yaml
test:
  coverage:
    reports:
      terminal: False  # Disable the terminal table (True by default)
      xml: True  # Enable XML report (.build/coverage.xml)
      html: True  # Enable HTML report (.build/htmlcov)
```

To see a much more verbose coverage report, set the `terminal` field to a dictionary that includes `"verbose": true`:

```yaml
test:
  coverage:
    reports:
      terminal:
        verbose: true  # Show verbose coverage information in the terminal.
```

Then, you will see table outputs like this:

```shell
===================================== Coverage Profile ========================================
                MyContract Coverage

                         Func   Stmts   Miss    Cover
 ─────────────────────────────────────────────────────
                  __builtin__       2      0   100.0%
            _immutable_number       0      0   100.0%
                      _number       0      0   100.0%
                 foo_method()       1      0   100.0%
          foo_method(uint256)       1      0   100.0%
  foo_method(uint256,uint256)       3      0   100.0%
                  view_method       1      0   100.0%

           line=0.0%, func=0.0%
```

This is useful when trying to find the missing areas to cover.
The HTML report also supports `verbose: true` and it will show similar tables.

```{note}
You may notice methods with zero statements.
```

One example of a method with zero statements may be from an auto-generated getter method for a public variable; certain versions of Vyper do not contain source mappings for these methods.
However, Ape will still check to see if this method has been called in your tests.
To get 100% coverage, you must call these methods in your tests.

```{note}
Notice some methods use the full selector while others don't.
```

Methods that use the selector mean that their short name is shared with other methods.
This happens in Vyper from auto-generated kwarg-based methods.
Thus, the full selector is used to distinguish the methods in the coverage (and gas) reports.

Much like gas reporting, you can also exclude contracts and methods from tracking coverage using your `ape-config.yaml` file.
The following demonstrates how to do this:

```yaml
test:
  coverage:
    exclude:
      - method_name: DEBUG_*         # Exclude all methods starting with `DEBUG_`.
      - contract_name: MockToken     # Exclude all methods in contract named `MockToken`.
      - contract_name: PoolContract  # Exclude methods starting with `reset_` in `PoolContract`.
        method_name: reset_*
```
