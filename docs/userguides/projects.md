# Developing Projects with Ape

Use `ape` to create blockchain projects. A common project structure looks like this:

```
project              # The root project directory
├── contracts/       # Project source files, such as '.sol' or '.vy' files
├── tests/           # Project tests, ran using the 'ape test' command
├── scripts/         # Project scripts, such as deploy scripts, ran using the 'ape run <name>' command
└── ape-config.yaml  # The ape project configuration file
```

See the [Configuration guide](config.md) for a more detailed explanation of settings you can
use in your `ape-config.yaml` files.

## Compiling Contracts

The project manager object is a representation of your current project. Access it from the root `ape` namespace:

```python
from ape import project
```

Your `project` contains all the "relevant" files, such as source files in the `contracts/` directory. The 
`contracts/` directory is where compilers look for contracts to compile. File extensions found within the `contracts/` 
directory determine which compiler plugin `ape` uses. Make sure to install the compiler plugins you need if they are 
missing by adding them to your `ape-config.yaml`'s `plugin` section, or manually adding via the following:

```bash
ape plugins install solidity vyper
```

Then, use the following command to compile all contracts in the `contracts/` directory:

```bash
ape compile
```

**NOTE**: Compiler plugins download missing compiler version binaries, based on the contracts' pragma-spec.

The contract types are then accessible from the `project` manager; deploy them in the `console` or in scripts:

```python
from ape import accounts, project

a = accounts.load("metamask_0")
a.deploy(project.MyContract)
```

## Networks

The default provider for the development network is the 
[Ethereum Tester provider](https://github.com/ethereum/eth-testers). However, you can change the default provider per
network using the `ape-config.yaml` file. 

```yaml
ethereum:
  development:
    default_provider: hardhat
```

For specifying the network in an ad-hoc fashion, commands such as `run`, `test`, and `console` offer a `--network` 
option:

```bash
ape run deploy --network ethereum:local:hardhat
```

**NOTE**: If you are using the default ecosystem or network, you can omit them from the option:

```bash
ape run deploy --network ::hardhat
```

## Testing

You can test your project using the `ape test` command. The `ape test` command comes with the core-plugin `ape-test`. 
The `ape-test` plugin extends the popular python testing framework
[pytest](https://docs.pytest.org/en/6.2.x/contents.html).

### Test Structure

Tests must be located in a project's `tests/` directory. Each test file must start with `test_` and have the `.py`
extension, such as `test_my_contract.py`. Each test method within the file must also start with `test_`. The following
is an example test:

```python
def test_add():
    assert 1 + 1 == 2
```

### Fixtures

Fixtures are any type of re-usable instances of something with configurable scopes. `pytest` handles passing fixtures 
into each test method as test-time. You can define your own fixtures or use existing ones. The `ape-test` plugin comes 
with fixtures you will likely want to use:

#### accounts fixture

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

#### project fixture

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

### Test Pattern

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
    owner_is_owner = my_contract.foo(sender=owner)
    assert owner_is_owner

    other_is_owner = my_contract.foo(sender=other)
    assert not other_is_owner
```

### Test Providers

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
