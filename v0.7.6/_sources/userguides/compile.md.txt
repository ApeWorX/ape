# Compile

Compile your project using the following command:

```bash
ape compile
```

Configure the location Ape looks for contracts by editing the `contracts_folder` key in your project's `ape-config.yaml` file:

```yaml
contracts_folder: src  # Default is 'contracts/'
```

## The JSON Compiler

Ape ships with a compiler that is able to compile `.json` files.
This compiler is useful for the following:

1. **Interfaces**: If you know the address of an existing contract, you can include its ABI in your project and create a contract wrapper around it:

```python
from ape import project

# Comes from a file named `MyInterface.json` in the contracts/ folder.
my_interface = project.MyInterface
address = "0x1234556b5Ed9202110D7Ecd637A4581db8b9879F"

# Instantiate a deployed contract using the local interface.
contract = my_interface.at(address)

# Call a method named `my_method` found in the local contract ABI.
contract.my_method()
```

2. **Pre-existing Contract Types**: If you have a contract type JSON that was compiled elsewhere, you can include it in your project.
   This is useful if you are unable or unwilling to install a compiler.

3. **Raw Compiler Output**: If you have an artifact with binary compiled elsewhere, you can include it in your project.
   This is useful if you want to use contracts from much larger projects as dependency for your test cases.

**WARN**: You may have to adjust name and source ID similarly to raw contract-type output.

## Other Compiler Plugins

If your project includes Solidity (`.sol`) or Vyper (`.vy`) files, you will have to install additional compilers.
To include additional compilers in your project, you can add the plugins to the `plugins` list in your `ape-config.yaml` or install them using the CLI.
For information on how to configure plugins in your project, follow [this guide](./installing_plugins.html).

## Ignore Files

You can configure files to be ignored from compilation.
By default, Ape ignores files `package.json`, `package-lock.json`, `tsconfig.json`.
To override this list, edit your `ape-config.yaml` similarly:

```yaml
compile:
  exclude:
    - "*package.json"
    - "*package-lock.json"
    - "*tsconfig.json"
    - "*custom.json"  # Append a custom ignore
```

**NOTE**: You must include the defaults in the list when overriding if you wish to retain them.

## Dependencies

In Ape, compiler plugins typically let you have dependencies.
See [this guide](./dependencies.html) to learn more about configuring dependencies in Ape.

To always compile dependencies in Ape during the `ape compile` command, use the CLI flag `--include-dependencies`:

```shell
ape compile --include-dependencies
```

Alternatively, configure it to always happen:

```yaml
compile:
  use_dependencies: true
```

## Settings

Generally, configure compiler plugins using your `ape-config.yaml` file.
For example, when using the `vyper` plugin, you can configure settings under the `vyper` key:

```yaml
vyper:
  version: 0.3.10
```

You can also configure adhoc settings in Python code:

```python
from pathlib import Path
from ape import compilers

settings = {"vyper": {"version": "0.3.7"}, "solidity": {"version": "0.8.0"}}
compilers.compile(
   ["path/to/contract.vy", "path/to/contract.sol"], settings=settings
)

# Or, more explicitly:
vyper = compilers.get_compiler("vyper", settings=settings["vyper"])
vyper.compile([Path("path/to/contract.vy")])

solidity = compilers.get_compiler("solidity", settings=settings["solidity"])
vyper.compile([Path("path/to/contract.sol")])
```

## Compile Source Code

Instead of compiling project source files, you can compile code (str) directly:

```python
from ape import accounts, compilers

CODE = """
   ... source code here
"""

container = compilers.compile_source(
   "vyper",
   CODE,
   settings={"vyper": {"version": "0.3.7"}}, 
   contractName="MyContract",
)

owner = accounts.test_accounts[0]

instance = container.deploy(sender=owner)
```
