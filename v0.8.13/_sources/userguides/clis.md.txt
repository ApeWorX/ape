# CLIs

Ape uses the [click framework](https://click.palletsprojects.com/en/8.1.x/) for handling all CLI functionality.
There are CLIs found in a couple areas in the Ape framework:

1. Plugins
2. Scripts

Both plugins and scripts utilize `click` for their CLIs.

For plugins, CLIs are an option for extending the framework.
You can read more about plugin development and CLIs in the [developing plugins guide](./developing_plugins.html).

Scripts utilize CLIs as an option for users to develop their scripts.
You can read more about scripting and CLIs in the [scripting guide](./scripts.html).

This guide is for showcasing utilities that ship with Ape to assist in your CLI development endeavors.

## Ape Context Decorator

The [@ape_cli_context](../methoddocs/cli.html#ape.cli.options.ape_cli_context) gives you access to all the root Ape objects (`accounts`, `networks` etc.), the ape logger, and an [abort](../methoddocs/cli.html#ape.cli.options.ApeCliContextObject.abort) method for stopping execution of your CLI gracefully.
Here is an example using all of those features from the `cli_ctx`:

```python
import click
from ape.cli import ape_cli_context


@click.command()
@ape_cli_context()
def cmd(cli_ctx):
    cli_ctx.logger.info("Test")
    account = cli_ctx.account_manager.load("metamask")
    cli_ctx.abort(f"Bad account: {account.address}")
```

In Ape, it is easy to extend the CLI context object and use the extended version in your CLIs:

```python
from ape.cli import ApeCliContextObject, ape_cli_context
import click

class MyManager:
   """My custom manager."""

class CustomContext(ApeCliContextObject):
   my_manager: MyManager = MyManager()
   """Add new managers to your custom context"""
   
   @property
   def signer(self):
      """Utilize existing managers in your custom context."""
      return self.account_manager.load("my_account")

@click.command()
@ape_cli_context(obj_type=CustomContext)
def cli(cli_ctx):
    # Access your manager.
    print(cli_ctx.my_manager)
    # Access other Ape managers.
    print(cli_ctx.account_manager)
```

## Network Tools

The [@network_option()](../methoddocs/cli.html#ape.cli.options.network_option) allows you to select an ecosystem, network, and provider.
To specify the network option, use values like:

```shell
--network ethereum
--network ethereum:sepolia
--network ethereum:mainnet:alchemy
--network ::foundry
```

To use default values automatically, omit sections of the choice, but leave the semi-colons for parsing.
For example, `::test` means to use the default ecosystem and network and the `test` provider.

Use `ecosystem`, `network`, and `provider` argument names in your command implementation to access their corresponding class instances:

```python
import click
from ape.cli import network_option

@click.command()
@network_option()
def cmd(provider):
   # This command only needs the provider.
   click.echo(provider.name)

@click.command()
@network_option()
def cmd_2(ecosystem, network, provider):
   # This command uses all parts of the parsed network choice.
   click.echo(ecosystem.name)
   click.echo(network.name)
   click.echo(provider.name)
```

The [ConnectedProviderCommand](../methoddocs/cli.html#ape.cli.commands.ConnectedProviderCommand) automatically uses the `--network` option and connects to the network before any of your code executes and then disconnects afterward.
This is useful if your script or command requires a provider connection in order for it to run.
Additionally, specify `ecosystem`, `network`, or `provider` in your command function if you need any of those instances in your `ConnectedProviderCommand`, just like when using `network_option`.

```python
import click
from ape.cli import ConnectedProviderCommand

@click.group()
def cli():
    pass

 @cli.command(cls=ConnectedProviderCommand)
def cmd_1(network, provider):
   click.echo(network.name)
   click.echo(provider.is_connected)  # True

 @cli.command(cls=ConnectedProviderCommand)
def cmd_2(provider):
   click.echo(provider.is_connected)  # True

 @cli.command(cls=ConnectedProviderCommand)
def cmd_3():
   click.echo("Using params from ConnectedProviderCommand is optional")
```

## Account Tools

Use the [@account_option()](../methoddocs/cli.html#ape.cli.options.account_option) for adding an option to your CLIs to select an account.
This option does several things:

1. If you only have a single account in Ape (from both test accounts _and_ other accounts), it will use that account as the default.
   (this case is rare, as most people have more than one test account by default).
2. If you have more than one account, it will prompt you to select the account to use.
3. You can pass in an account alias or index to the option flag to have it use that account.
4. It allows you to specify test accounts by using a choice of `TEST::{index_of_test_account}`.

Thus, if you use this option, no matter what, your script will have an account to use by the time the script starts.
Here is an example:

```python
import click
from ape.cli import account_option


@click.command()
@account_option()
def cmd(account):
    # Will prompt the user to select an account if needed.
    click.echo(account.alias)
```

And when invoking the command from the CLI, it would look like the following:
(where `<prefix>` is either `ape run` for scripts or `ape <custom-plugin-cmd>` for plugins)

```shell
<prefix> cmd  # Use the default account.
<prefix> cmd --account 0  # Use first account that would show up in `select_account()`.
<prefix> cmd --account metamask  # Use account with alias "metamask".
<prefix> cmd --account TEST::0  # Use the test account at index 0.
```

Alternatively, you can call the [select_account()](../methoddocs/cli.html#ape.cli.choices.select_account) directly to have more control of when the account gets selected:

```python
import click
from ape.cli import select_account


@click.command()
def cmd():
   account = select_account("Select an account to use")
   click.echo(f"You selected {account.address}.")
```

Similarly, there are a couple custom arguments for aliases alone that are useful when making CLIs for account creation.
If you use [@existing_alias_argument()](../methoddocs/cli.html#ape.cli.arguments.existing_alias_argument) and specify an alias does not already exist, it will error.
And visa-versa when using [@non_existing_alias_argument()](../methoddocs/cli.html#ape.cli.arguments.non_existing_alias_argument).

```python
import click
from ape.cli import existing_alias_argument, non_existing_alias_argument


@click.command()
@existing_alias_argument()
def delete_account(alias):
    # We know the alias is an existing account at this point.
    click.echo(alias)


@click.command()
@non_existing_alias_argument()
def create_account(alias):
    # We know the alias is not yet used in Ape at this point.
    click.echo(alias)
```

You can control additional filtering of the accounts by using the `account_type` kwarg.
Use `account_type` to filter the choices by specific types of [AccountAPI](../methoddocs/api.html#ape.api.accounts.AccountAPI), or you can give it a list of already known accounts, or you can provide a callable-filter that takes an account and returns a boolean.

```python
import click
from ape import accounts
from ape.cli import existing_alias_argument, select_account
from ape_accounts.accounts import KeyfileAccount

# NOTE: This is just an example and not anything specific or recommended.
APPLICATION_PREFIX = "<FOO_BAR>"

@click.command()
@existing_alias_argument(account_type=KeyfileAccount)
def cli_0(alias):
   pass

@click.command()
@existing_alias_argument(account_type=lambda a: a.alias.startswith(APPLICATION_PREFIX))
def cli_1(alias):
   pass

# Select from the given accounts directly.
my_accounts = [accounts.load("me"), accounts.load("me2")]
selected_account = select_account(account_type=my_accounts)
```

## Contract File Paths

Does your CLI interact with contract source files?
(Think `ape compile`).

If so, use the `@contract_file_paths_argument()` decorator in your CLI.

```python
from pathlib import Path
import click

from ape.cli import contract_file_paths_argument

@click.command()
@contract_file_paths_argument()
def cli(file_paths: set[Path]):
   # Loop through all source files given (or all source files in the project).
    for path in file_paths:
        click.echo(f"Source found: {path}")
```

When using the `@contract_file_paths_argument()` decorator, you can pass any number of source files as arguments.
When not passing any source file(s), `@contract_file_paths_argument()` defaults to all sources in the local project.
That is why `ape compile` compiles the full project and `ape compile MySource.vy` only compiles `MySource.vy` (and whatever else it needs / imports).
Use `@contract_file_paths_argument()` for any similar use-case involving contract source files.
