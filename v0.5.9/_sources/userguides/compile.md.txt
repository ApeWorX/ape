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

**WARN**: You may have to adjust the name and source ID of the contract type in the JSON to match the new file name in your project.

## Other Compiler Plugins

If your project includes Solidity (`.sol`) or Vyper (`.vy`) files, you will have to install additional compilers.
To include additional compilers in your project, you can add the plugins to the `plugins` list in your `ape-config.yaml` or install them using the CLI.
For information on how to configure plugins in your project, follow [this guide](./installing_plugins.html).

## Ignore Files

You can configure files to be ignored from compilation.
By default, Ape ignores files `package.json`, `package-lock.json`, `tsconfig.json`.
To override this list, edit your `ape-config.yaml` similarly:

```yaml
compiler:
  ignore_files:
    - "*package.json"
    - "*package-lock.json"
    - "*tsconfig.json"
    - "*custom.json"  # Append a custom ignore
```

**NOTE**: You must include the defaults in the list when overriding if you wish to retain them.
