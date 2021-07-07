import json
from typing import List

import click
from eth_account import Account as EthAccount  # type: ignore
from eth_utils import to_bytes

from ape import accounts
from ape.utils import notify

# NOTE: Must used the instantiated version of `AccountsContainer` in `accounts`
container = accounts.containers["accounts"]


class Alias(click.Choice):
    name = "alias"

    def __init__(self):
        # NOTE: we purposely skip the constructor of `Choice`
        self.case_sensitive = False

    @property
    def choices(self) -> List[str]:  # type: ignore
        # NOTE: This is a hack to lazy-load the aliases so CLI invocation works properly
        return list(accounts.aliases)


@click.group(short_help="Manage local accounts")
def cli():
    """
    Command-line helper for managing local accounts. You can unlock local accounts from
    scripts or the console using the accounts.load() method.
    """


# Different name because `list` is a keyword
@cli.command(name="list", short_help="List available accounts")
def _list():
    if len(accounts) == 0:
        notify("WARNING", "No accounts found.")
        return

    elif len(accounts) > 1:
        click.echo(f"Found {len(accounts)} accounts:")

    else:
        click.echo("Found 1 account:")

    for account in accounts:
        alias_display = f" (alias: '{account.alias}')" if account.alias else ""
        click.echo(f"  {account.address}{alias_display}")


@cli.command(short_help="Create a new keyfile account with a random private key")
@click.argument("alias")
def generate(alias):
    if alias in accounts.aliases:
        notify("ERROR", f"Account with alias '{alias}' already exists")
        return

    path = container.data_folder.joinpath(f"{alias}.json")
    extra_entropy = click.prompt(
        "Add extra entropy for key generation...",
        hide_input=True,
    )
    account = EthAccount.create(extra_entropy)
    passphrase = click.prompt(
        "Create Passphrase",
        hide_input=True,
        confirmation_prompt=True,
    )
    path.write_text(json.dumps(EthAccount.encrypt(account.key, passphrase)))

    notify("SUCCESS", f"A new account '{account.address}' has been added with the id '{alias}'")


# Different name because `import` is a keyword
@cli.command(name="import", short_help="Add a new keyfile account by entering a private key")
@click.argument("alias")
def _import(alias):
    if alias in accounts.aliases:
        notify("ERROR", f"Account with alias '{alias}' already exists")
        return

    path = container.data_folder.joinpath(f"{alias}.json")
    key = click.prompt("Enter Private Key", hide_input=True)
    try:
        account = EthAccount.from_key(to_bytes(hexstr=key))
    except Exception as error:
        notify("ERROR", f"Key can't be imported {error}")
        return
    passphrase = click.prompt(
        "Create Passphrase",
        hide_input=True,
        confirmation_prompt=True,
    )
    path.write_text(json.dumps(EthAccount.encrypt(account.key, passphrase)))

    notify("SUCCESS", f"A new account '{account.address}' has been added with the id '{alias}'")


@cli.command(short_help="Change the password of an existing account")
@click.argument("alias", type=Alias())
def change_password(alias):
    account = accounts.load(alias)
    account.change_password()
    notify("SUCCESS", f"Password has been changed for account '{alias}'")


@cli.command(short_help="Delete an existing account")
@click.argument("alias", type=Alias())
def delete(alias):
    account = accounts.load(alias)
    account.delete()
    notify("SUCCESS", f"Account '{alias}' has been deleted")
