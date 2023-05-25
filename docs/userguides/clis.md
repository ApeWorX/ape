# CLIs

Ape uses the [click framework](https://click.palletsprojects.com/en/8.1.x/) for handling all CLI functionality.
There are CLIs found in a couple spots in the Ape framework:

1. Plugins
2. Scripts

Both plugins and scripts utilize `click` for their CLIs.

For plugins, CLIs are an option for extending the framework.
You can read more about plugin development and CLIs in the [developing plugins guide](./developing_plugins.md).

Scripts utilize CLIs as an option for users to develop their scripts.
You can read more about scripting and CLIs in the [scripting guide](./scripts.md).

This guide is for showcasing some of their utilities that ship with Ape to assist in your CLI development endeavors.

## Ape Context Decorator

The `@ape_cli_context` gives you access to all the root Ape objects as well as utilities for easily aborting the execution and access to the logger:

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

## Network Tools

The `@network_option()` allows you to select a network choices for parsing.
In combination with the `NetworkBoundCommand` type, you can cause the connection to occur before any code in your CLI executes.
This is useful if your script or command requires a connection to a node provider in order for it to run.

```python
import click
from ape import networks
from ape.cli import network_option, NetworkBoundCommand


@click.command()
@network_option()
def cmd(network):
    # Choices like "ethereum" or "polygon:local:test".
    click.echo(network)


@click.command(cls=NetworkBoundCommand)
@network_option()
def cmd(network):
    # Fails if we are not connected.
    click.echo(networks.provider.network.name)
```

## Account Tools

Use the `@account_option()` for adding an option to your CLIs to selecting accounts.
This option does several things:

1. If you only have a single non-development account in Ape, it will use that account as the default.
2. If you more than one, it will prompt you to select the account to use.
3. You can pass in account alias or index to the option flag to have it use that account.
4. It allows you to specify test accounts by using a choice of `TEST::{index_of_test_account}`.

So if you use this option, no matter what, your script will have an account to use by the time the script starts.
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

And when invoking the command from the CLI, it would like something like (where `<prefix>` is either `ape run` for scripts or `ape <custom-plugin-cmd>` for plugins):

```shell
<prefix> cmd  # Use the default account.
<prefix> cmd --account 0  # Use first account that would show up in `get_user_selected_account()`.
<prefix> cmd --account metamask  # Use account with alias "metamask".
<prefix> cmd --account TEST::0  # Use the test account at index 0.
```

Alternatively, you can call the `get_user_selected_account()` directly to have more control of when the account gets selected:

```python
import click
from ape.cli import get_user_selected_account


@click.command()
def cmd():
    account = get_user_selected_account("Select an account to use")
    click.echo(f"You selected {account.address}.")
```

Similarly, there are a couple custom arguments for aliases alone that are useful when making CLIs for account creation.
If you use `@existing_alias_argument()` and specify an alias does not already exist, it will error.
And visa-versa when using `@non_existing_alias_argument()`

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
