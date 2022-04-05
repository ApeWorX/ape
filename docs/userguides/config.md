# Developing Projects with Ape

Use `ape` to create blockchain projects. A common project structure looks like this:

```
project                             # The root project directory
├── contracts/                      # Project source files, such as '.sol' or '.vy' files
    └── smart_contract_example.sol  # Sample of a smart contract
├── tests/                          # Project tests, ran using the 'ape test' command
    └── test_sample.py              # Sample of a test to run against your sample contract
├── scripts/                        # Project scripts, such as deploy scripts, ran using the 'ape run <name>' command
    └── deploy_sample.py            # Sample script to automate a specification of an ape project
├── ape-config.yaml                 # The ape project configuration file
```

`ape-config.yaml` is file allows you to configure ape project and it dependencies. 

[Configuration guide](config.md) for a more detailed explanation of settings you can
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
ape plugins install solidity
# OR
ape plugins install vyper
```

Then, use the following command to compile all contracts in the `contracts/` directory:

**NOTE**: You must be in the project root directory before running

```bash
$ pwd && ls
    ~/project_name
LICENSE  README.md  ape-config.yaml  contracts  scripts  tests
$ ape compile
```

**NOTE**: Compiler plugins download missing compiler version binaries, based on the contracts' pragma-spec.

The contract containers are then accessible from the `project` manager; deploy them in the `console` or in scripts:

```python
from ape import accounts, project

account = accounts.load("my_account_alias")
account.deploy(project.MyContract)
```

**NOTE**: You can also deploy contracts from the container itself:

```python
from ape import accounts, project

account = accounts.load("my_account_alias")
project.MyContract.deploy(sender=account)
```

### Dependencies

To set up dependencies in your ``ape-config.yaml`` file, follow [this guide](https://docs.apeworx.io/ape/stable/userguides/config.html#dependencies).
If you are using dependencies from a remote source, they will download when you run `ape compile` or other commands that compile beforehand.
Dependencies only need to download and compile once.

You can access dependency contracts off your root project manager:

```python
from ape import accounts, project

dependency_contract = project.dependencies["my_dependency"].DependencyContractType
my_account = accounts.load("alias")
deployed_contract = my_account.deploy(dependency_contract, "argument")
print(deployed_contract.address)
```

## Networks

The default provider for the development network is the
[Ethereum Tester provider](https://github.com/ethereum/eth-tester). However, you can change the default provider per
network using the `ape-config.yaml` file.

```yaml
ethereum:
  development:
    default_provider: hardhat
```

For specifying the network in an ad-hoc fashion, commands such as `run`, `test`, and `console` offer a `--network`
option:

```bash
ape console --network ethereum:local:hardhat
```

**NOTE**: If you are using the default ecosystem or network, you can omit them from the option:

```bash
ape console --network ::hardhat
```

## Scripts

The scripts folder is a set of files to automate your ape project to your specification. 
For example you should keep a deployment script here.

You can write scripts that run using the `ape run` command. The `ape run` command will register and run Python
files defined under the `scripts/` directory that do not start with an `_` underscore. If the scripts take
advantage of utilities from our [`ape.cli`](../methoddocs/cli.html#ape-cli) submodule,
you can build a [Click](https://click.palletsprojects.com/) command line interface
by defining a `click.Command` or `click.Group` object called `cli` in your file.
Otherwise, if the script has a `main()` method, it will execute that method when called.

Note that by default, `cli` scripts do not have
[`ape.cli.network_option`](../methoddocs/cli.html?highlight=options#ape.cli.options.network_option)
installed, giving you more flexibility in how you define your scripts.
`main` scripts will always provide a network option to the call.

## Testing

Testing an ape project is important and easy.

Testing rules:
-   All tests must be stored under `tests/`. 
-   Each test file must start with `test_` and end with the `.py` extension.
-   Each function must start with `test_`

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

```python
def test_account_balance(owner):
    # ^ use the 'project' fixture from the 'ape-test' plugin
    actual = my_project.balanceOf(owner)
    expect = quantity
    assert actual == expect
```

### Fixtures

Fixtures are any type of re-usable instances of something with configurable scopes. `pytest` handles passing fixtures
into each test method as test-time. To learn more about [fixtures](https://docs.pytest.org/en/7.1.x/explanation/fixtures.html)

Define fixtures for static data used by tests. This data can be accessed by all tests in the suite unless specified otherwise. This could be data as well as helpers of modules which will be passed to all tests.

A commone place to define fixtures are in the **conftest.py** which should be saved under the test directory:

conftest.py is used to import external plugins or modules. By defining the following global variable, pytest will load the module and make it available for its test.

You can define your own fixtures or use existing ones. The `ape-test` plugin comes
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
# NOTE this function does not start with test_ ape test will not test this function


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

#### Project Fixture

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

### Ape Testing Commands

```bash
ape test
```

To run a particular test:

```bash
ape test test_my_contract.py
```
One of the powerful tools to step into the test is out **Interactive Mode**

Use ape test ``-I`` to open the interactive mode at the point of exception. This allows the user to inspect the point of failure in your tests.

```bash
ape test test_my_contract -I -s
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

#### Samele of test directory and files 

When writing your test **files and functions**. They must begin with **test_** for `ape test` to recognize and run the test.
```
my_project/                     # The root project directory
    └── tests/                  # Project tests folder, ran using the 'ape test' command to run all test within the folder.
        └── conftest.py         # A file to define global variable for testing 
        └── test_accounts.py    # A test file, if you want to ONLY run one test file you can use 'ape test test_accounts.py' command
        └── test_mint.py        # A test file

```