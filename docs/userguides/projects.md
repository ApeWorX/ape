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

## Scripts

The scripts folder contains project automation scripts, such as deploy scripts, as well as other executable jobs, such as scripts for running simulations.
To learn more about scripting in Ape, see [the scripting guide](./scripts.html).

## Testing

Use tests to verify your project.
You can test your project using the `ape test` command.
The `ape test` command comes with the core-plugin `ape-test`.
The `ape-test` plugin extends the popular python testing framework [pytest](https://docs.pytest.org/en/6.2.x/contents.html).
Testing is a complex topic; learn more about testing using Ape framework [here](./testing.html).
