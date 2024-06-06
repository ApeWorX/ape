# Developing Plugins

Your plugin project can be any type of python project, so long as its package name starts with `ape-` (such as `ape-ethereum`).
The module and plugin directory name must start with `ape_` (such as `ape_ethereum`).
To create an `ape` plugin, implement one or more API classes from the `ape.api` namespace and/or add key
`ape_cli_subcommands` to your entry-points list in your project's `setup.py`, depending on what type of plugin you want to create.
This guide is intended to assist in both of those use cases.

The following is a list of example plugins to use as a reference when developing plugins:

- [the Solidity plugin](https://github.com/apeworx/ape-solidity), an example `CompilerAPI`
- [the Infura plugin](https://github.com/apeworx/ape-infura), an example `ProviderAPI`
- [the Trezor plugin](https://github.com/apeworx/ape-trezor), an example `AccountAPI`
- [the Tokenlists plugin](https://github.com/apeworx/ape-tokens), an example CLI Extension

## Initialize a Plugin Project

As previously mentioned, a plugin project is merely a python project.
However, you can optionally use this [project template](https://github.com/ApeWorX/project-template) for initializing your plugin.

```{note}
This template is primarily designed for plugins built within the ApeWorX team organization; not everything may apply.
```

It is okay to delete anything that does not work or that you don't find helpful.
The template may be good to follow if you want to keep your plugin of similar quality to plugins developed by the ApeWorX team.

## Implementing API Classes

API classes (classes from the `ape.api` namespace) are primarily composed of abstract methods and properties that plugins must implement.
A benefit of the plugin system is that each plugin can implement these however they need, so long as they conform to the API interface.
Two plugins with the same API may do entirely different things and yet be interchangeable in their usage.

To implement an API, import its class and use it as a base-class in your implementation class.

```{warning}
The plugin will fail to work properly if you do not implement all the abstract methods.
```

```python
from ape.api import ProviderAPI
from web3 import Web3, HTTPProvider


class MyProvider(ProviderAPI):
    _web3: Web3 = None  # type: ignore
    
    def connect(self):
        self._web3  = Web3(HTTPProvider(str("https://localhost:1337")))

    """Implement rest of abstract methods"""
```

### Registering API Classes

Once you have finished implementing your API classes, you need to register them using the [@plugins.register](../methoddocs/plugins.html#ape.plugins.register) method decorator.

```python
from ape import plugins

# Here, we register our provider plugin so we can use it in 'ape'.
@plugins.register(plugins.ProviderPlugin)
def providers():
    # NOTE: 'MyProvider' defined in a prior code-block.
    yield "ethereum", "local", MyProvider
```

This decorator hooks into ape core and ties everything together by looking for all local installed site-packages that start with `ape_`.
Then, it will loop through these potential `ape` plugins and see which ones have created a plugin type registration.
If the plugin type registration is found, then `ape` knows this package is a plugin and attempts to process it according to its registration interface.

### CLI Plugins

The `ape` CLI is built using the python package [click](https://palletsprojects.com/p/click/).
To create a CLI plugin, create any type of `click` command (such as a `click.group` or a `click.command`).

`_cli.py`:

```python
import click

@click.group
def cli():
    """My custom commands."""


@cli.command()
def my_sub_cmd():
    """My subcommand."""
```

Then, register it using `entrypoints`, which is a built-in python registry of items declared in `setup.py`.

`setup.py`:

```python
...
entry_points={
    "ape_cli_subcommands": [
        "ape_myplugin=ape_myplugin._cli:cli",
    ],
},
...
```

```{note}
Typically, a `_cli.py` module is used instead of a `__init__.py` module for the location of the Click CLI group because it is logically separate from the Python module loading process.
```

If you try to define them together and use `ape` as a library as well, there is a race condition in the loading process that will prevent the CLI plugin from working.

For common `click` usages, use the `ape.cli` namespace.
For example, use the [@existing_alias_argument() decorator](../methoddocs/cli.html#ape.cli.arguments.existing_alias_argument)) when you need a CLI argument for specifying an existing account alias:
Follow [this guide](./clis.html) to learn more about what you can do with the utilities found in `ape.cli`.

```python
import click
from ape.cli import existing_alias_argument

@click.command()
@existing_alias_argument()
def my_cmd(alias):
  click.echo(f"{alias} is an existing account!")
```

## Using Plugins

Once you have finished implementing and registering your API classes, they will now be part of `ape`. For example,
if you implemented the `AccountAPI`, you can now use accounts created from this plugin. The top-level `ape` manager
classes are indifferent about the source of the plugin.

```python
from ape import accounts

# The manager can load accounts from any account-based plugin.
my_ledger_account = accounts.load("ledger_0")  # Created using the 'ape-ledger' plugin
my_trezor_account = accounts.load("trezor_0")  # Created using the 'ape-trezor' plugin
```

Similarly, if you implemented a `ProviderAPI`, that provider is now accessible in the CLI via the `--network` option:

```bash
ape console my_script --network ethereum:local:my_provider_plugin
```

```{note}
The `--network` option is available on the commands `test` and `console` as well as any CLI command that uses the [network option decorator](../methoddocs/cli.html?highlight=network_option#ape.cli.options.network_option).
```

To learn more about networks in Ape, follow [this guide](./networks.html).

When creating the CLI-based plugins, you should see your CLI command as a top-level command in the `ape --help` output:

```
Commands:
  ...
  my-plugin  Utilities for my plugin
  ...
```

To edit the description of the CLI command (or group), you can either set the `short_help` kwarg or use a doc-str on the command:

```python
import click


@click.command(short_help="Utilities for my plugin")
def cli():
    pass

""" Or """

@click.command()
def cli():
    """Utilities for my plugin"""
```

## Logging

Use Ape's logger in your plugin by importing it from the `ape.logging` module or by using it off the CLI context (from using the `@ape_cli_context` decorator).

### Import the logger from the logging module

```python
from ape.logging import logger

logger.info("This is a log message")
```

### Use the logger from the `@ape_cli_context`

```python
from ape.cli import ape_cli_context

@ape_cli_context()
def my_command(cli_ctx):
  cli_ctx.logger.info("my log message")
```
