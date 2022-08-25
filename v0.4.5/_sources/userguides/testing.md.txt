# Testing

Testing an ape project is important and easy.

## Test Structure

Tests must be located in a project's `tests/` directory. Each **test file** must start with `test_` and have the `.py` extension, such as `test_my_contract.py`.
Each **test method** within the file must also start with `test_`.
The following is an example test:

```python
def test_add():
    assert 1 + 1 == 2
```

**NOTE**: `pytest` assumes the *actual* value is on the left and the *expected* value is on the right.

## Test Pattern

Tests are generally divisible into three parts:

1. Set-up
2. Invocation
3. Assertion

In the example above, we created a fixture that deploys our smart-contract.
This is an example of a 'setup' phase.
Next, we need to call a method on our contract.
Let's assume there is an `authorized_method()` that requires the owner of the contract to make the transaction.
If the sender of the transaction is not the owner, the transaction will fail to complete and will revert.

This is an example of how that test may look:

```python
def test_authorization(my_contract, owner, not_owner):
    my_contract.set_owner(sender=owner)
    assert owner == my_contract.owner()

    with ape.reverts("!authorized"):
        my_contract.authorized_method(sender=not_owner)
```

```{note}
Ape has built-in test and fixture isolation for all pytest scopes.
To disable isolation add the `--disable-isolation` flag when running `ape test`
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

You can configure your accounts by changing the `mnemonic` or `number_of_accounts` settings in the `test` section of your `ape-config.yaml` file:

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

Out-of-the-box, your tests run using the `eth-tester` provider, which comes bundled with ape. If you have `geth` installed, you can use the `ape-geth` plugin that also comes with ape.

```bash
ape test --network ethereum:local:geth
```

Each testing plugin should work the same way. You will have access to the same test accounts.

Another option for testing providers is the [ape-hardhat plugin](https://github.com/ApeWorX/ape-hardhat), which does not come with `ape` but can be installed by including it in the `plugins` list in your `ape-config.yaml` file or manually installing it using the command:

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
Here is an example of a test function from a sample [NFT project](https://github.com/ApeAcademy/ERC721)

```python
def test_account_balance(project, owner, receiver, nft):
    quantity = 1
    nft.mint(receiver, quantity, ["0"], value=nft.PRICE() * quantity, sender=owner)
    actual = project.balanceOf(receiver)
    expect = quantity
    assert actual == expect
```

## Multi-chain Testing

The Ape framework supports connecting to alternative providers in tests.
The easiest way to achieve this is to use the `networks` provider context-manager.

```python
# Switch to Fantom mid test
def test_my_fantom_test(networks):
    # The test starts in 1 ecosystem but switches to another
    assert networks.provider.network.ecosystem.name == "ethereum"
    
    with networks.fantom.local.use_provider("test") as provider:
        assert provider.network.ecosystem.name == "fantom"
    
    # You can also use the context manager like this:
    with networks.parse_network_choice("fantom:local:test") as provider:
       assert provider.network.ecosystem.name == "fantom"
```

You can also set the network context in a context-manager pytest fixture:

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
