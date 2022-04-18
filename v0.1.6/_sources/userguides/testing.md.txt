# Testing

Testing an ape project is important and easy.

## Test Structure

Tests must be located in a project's `tests/` directory. Each **test file** must start with `test_` and have the `.py`
extension, such as `test_my_contract.py`. Each **test method** within the file must also start with `test_`. The following
is an example test:

```python
def test_add():
    assert 1 + 1 == 2
```
## Test Pattern

Tests are generally divisible into three parts:

1. Set-up
2. Invocation
3. Assertion

In the example above, we created a fixture that deploys our smart-contract. This is an example of a 'setup' phase.
Next, we need to call a method on our contract. Let's assume there is a method called `is_owner()` that returns `True`
when it is the owner of the contract making the transaction.

This is an example of how that test may look:

```python
def test_is_owner(my_contract, owner, other):
    my_contract.set_owner(sender=owner)
    assert owner == my_contract.owner()

    other_is_owner = my_contract.foo(sender=other)
    assert not other_is_owner
```

## Fixtures

Fixtures are any type of reusable instances of something with configurable scopes. `pytest` handles passing fixtures
into each test method as test-time. To learn more about [fixtures](https://docs.pytest.org/en/7.1.x/explanation/fixtures.html)

Define fixtures for static data used by tests. This data can be accessed by all tests in the suite unless specified otherwise. This could be data as well as helpers of modules which will be passed to all tests.

A common place to define fixtures are in the **conftest.py** which should be saved under the test directory:

conftest.py is used to import external plugins or modules. By defining the following global variable, pytest will load the module and make it available for its test.

You can define your own fixtures or use existing ones. The `ape-test` plugin comes
with fixtures you will likely want to use:

### accounts fixture

You have access to test accounts. These accounts are automatically funded, and you can use them to transact in your
tests. Access each [test account](../methoddocs/api.html?highlight=testaccount#ape.api.accounts.TestAccountAPI) by
index from the `accounts` fixture:

```python
def test_my_method(accounts):
    owner = accounts[0]
    other = accounts[1]
```

For code readability and sustainability, create your own fixtures using the `accounts` fixture:

```python
import pytest


@pytest.fixture
def owner(accounts):
    return accounts[0]


@pytest.fixture
def other(accounts):
    return accounts[1]


def test_my_method(owner, other):
    ...
```

You can configure your accounts by changing the `mnemonic` or `number_of_accounts` settings in the `test` section of
your `ape-config.yaml` file:

```yaml
test:
  mnemonic: test test test test test test test test test test test junk
  number_of_accounts: 5
```

If you are using a fork-provider, such as [Hardhat](https://github.com/ApeWorX/ape-hardhat), you can use impersonated accounts by accessing random addresses off the fixture:

```python
@pytest.fixture
def vitalik(accounts):
    return accounts["0xab5801a7d398351b8be11c439e05c5b3259aec9b"]
```

### project fixture

You also have access to the `project` you are testing. You will need this to deploy your contracts in your tests.

```python
import pytest


@pytest.fixture
def owner(accounts):
    return accounts[0]


@pytest.fixture
def my_contract(project, owner):
    # ^ use the 'project' fixture from the 'ape-test' plugin
    return owner.deploy(project.MyContract)
```

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

Out-of-the-box, your tests run using the `eth-tester` provider, which comes bundled with ape. If you have `geth`
installed, you can use the `ape-geth` plugin that also comes with ape.

```bash
ape test --network ethereum:local:geth
```

Each testing plugin should work the same way. You will have access to the same test accounts.

Another option for testing providers is the [ape-hardhat plugin](https://github.com/ApeWorX/ape-hardhat), which does
not come with `ape` but can be installed by including it in the `plugins` list in your `ape-config.yaml` file or
manually installing it using the command:

```bash
ape plugins install hardhat
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
Here is a sample of test function from a sample [NFT](https://github.com/ApeAcademy/generative-nft)

```python
def test_account_balance(owner, receiver, buyers, nft)):
    # ^ use the 'project' fixture from the 'ape-test' plugin
    quantity = 1
    nft.mint(quantity, ["0"], value=nft.PRICE() * quantity, sender=receiver)
    actual = project.balanceOf(owner)
    expect = quantity
    assert actual == expect
```
