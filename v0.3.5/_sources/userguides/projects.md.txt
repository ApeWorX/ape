# Developing Projects with Ape

Use `ape init` to create your project. A common project structure looks like this:

```
project                             # The root project directory
├── contracts/                      # Project source files, such as '.sol' or '.vy' files
    └── smart_contract_example.sol  # Sample of a smart contract
├── tests/                          # Project tests, ran using the 'ape test' command
    └── test_sample.py              # Sample of a test to run against your sample contract
├── scripts/                        # Project scripts, such as deploy scripts, ran using the 'ape run   <`name>' command
    └── deploy.py                   # Sample script to automate a deployment of an ape project
└── ape-config.yaml                 # The ape project configuration file
```


 [Configuration guide](../userguides/config.md) for a more detailed explanation of settings you can
use in your `ape-config.yaml` files.

## Compiling Contracts

The project manager object is a representation of your current project. Access it from the root `ape` namespace:

```python
from ape import project
```

Your `project` contains all the "relevant" files, such as source files in the `contracts/` directory. The
`contracts/` directory is where compilers look for contracts to compile. File extensions found within the `contracts/`
directory determines which compiler plugin `ape` uses. Make sure to install the compiler plugins you need if they are
missing by adding them to your `ape-config.yaml`'s `plugin` section, or manually adding via the following:

```bash
ape plugins install solidity vyper
```

Then, use the following command to compile all contracts in the `contracts/` directory:

```bash
ape compile
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

The scripts folder contains project automation scripts, such as deploy scripts, as well as other executable jobs, such as scripts for running simulations.

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


Use tests to verify your project. Testing is a complex topic, learn more about testing using Ape framework
[here](./testing.html)

You can test your project using the `ape test` command. The `ape test` command comes with the core-plugin `ape-test`.
The `ape-test` plugin extends the popular python testing framework
[pytest](https://docs.pytest.org/en/6.2.x/contents.html).
