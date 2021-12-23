# Developing Projects

Use `ape` to create blockchain projects. A common project structure looks like this:

```
project         # The root project directory
├── contracts/  # Project source files, such as .sol or .vy files
├── tests/      # Project tests, ran using the 'ape test' command
└── scripts/    # Project scripts, such as deploy scripts, ran using the 'ape run <name>' command
```

## Compiling Contracts

The project manager object is a representation of your current project. Access it from the root `ape` namespace:

```python
from ape import project
```

Your `project` contains all the "relevant" files, such as source files in the `contracts/` directory. The 
`contracts/` directory is where compilers look for contracts to compile. File extensions found within the `contracts/` 
directory determine which compiler plugin ape uses. Make sure to install the compiler plugins you need if they are 
missing by adding them to your `ape-config.yaml`'s `plugin` section, or manually adding via the following:

```bash
ape plugins add solidity
ape plugins add vyper
```

Then, use the following command to compile all of the contracts in the `contracts/' directory:

```bash
ape compile
```

**WARNING**: Compiler plugins download missing compiler version binaries, based on the contracts' pragma-spec.

The contract types are then accessible from the `project` manager and can be deployed in the `console` or in scripts:

```python
from ape import accounts, project

a = accounts.load("metamask_0")
a.deploy(project.MyContract)
```
