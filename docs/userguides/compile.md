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

```{warning}
You may have to adjust name and source ID similarly to raw contract-type output.
```

## Other Compiler Plugins

If your project includes Solidity (`.sol`) or Vyper (`.vy`) files, you will have to install additional compilers.
To include additional compilers in your project, you can add the plugins to the `plugins` list in your `ape-config.yaml` or install them using the CLI.
For information on how to configure plugins in your project, follow [this guide](./installing_plugins.html).

## Exclude Files

You can configure files to be excluded from compilation.
By default, Ape excludes known non-contract files such as `package.json`, `package-lock.json`, `tsconfig.json`, or `.DS_Store`.
To append file-globs to the exclusions list, edit your `compile:exclude` config like this:

```yaml
compile:
  exclude:
    - "examples"  # Exclude all files in the examples/ directory
    - "*Mock.sol"  # Exclude all files ending in Mock.sol
    - r"(?!.*_mock\.vy$)"  # You can also use regex instead of globs (prefix with `r`).
```

You can also exclude files using the `--config-override` CLI option:

```shell
ape compile --config-override '{"compile": {"exclude": ["*Mock.sol"]}}'
```

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

When using the CLI, you can also specify settings using the `--config-override`.
This is not limited to compiler settings; you can include other settings, such as `"contracts_folder"`, which affects compiling.

```shell
ape compile --config-override '{"contracts_folder": "other_contracts", "vyper": {"evm_version": "paris"}, "solidity": {"evm_version": "paris"}}'
```

Finally, you can also configure settings in Python code:

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

## Output Extra

Sometimes, there are extra output styles you may want.
For example, to output minified ABI JSONs, use the following config:

```yaml
compile:
  output_extra:
     - ABI
```

Then, after compiling, you should notice minified ABI json files in your `.build/abi` folder.
This is useful if hosting these files on a web-server.

To see the full list of supported output-extra, see [the OutpuExtra enum documentation](../methoddocs/ape_compile.html#ape_compile.OutputExtras).
