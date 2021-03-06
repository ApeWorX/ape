import click

from ape.accounts import accounts

from .accounts import KeyfileAccount


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
        click.echo("No accounts found.")
        return

    elif len(accounts) > 1:
        click.echo(f"Found {len(accounts)} accounts:")

    else:
        click.echo("Found 1 account:")

    for account in accounts:
        alias_display = f" (alias: '{account.alias}')" if account.alias else ""
        click.echo(f"{account.address}{alias_display}")


@cli.command(short_help="Add a new account with a random private key")
@click.argument("alias")
def generate(alias):
    assert alias not in accounts.aliases
    a = KeyfileAccount.generate(accounts.path.joinpath(f"{alias}.json"))
    click.echo(f"A new account '{a.address}' has been added with the id '{alias}'")


# Different name because `import` is a keyword
@cli.command(name="import", short_help="Add a new account by entering a private key")
@click.argument("alias")
def _import(alias):
    if alias in accounts.aliases:
        click.echo(f"Account with alias '{alias}' already exists")
        return

    a = KeyfileAccount.from_key(accounts.DATA_FOLDER.joinpath(f"{alias}.json"))
    click.echo(f"A new account '{a.address}' has been added with the id '{alias}'")


@cli.command(short_help="Change the password of an existing account")
@click.argument("alias", type=click.Choice(accounts.aliases))
def change_password(alias):
    account = accounts.load(alias)
    if not isinstance(account, KeyfileAccount):
        click.echo(f"Account '{alias}' cannot change it's password")
        return

    account.change_password()
    click.echo(f"Password has been changed for account '{alias}'")


@cli.command(short_help="Delete an existing account")
@click.argument("alias", type=click.Choice(accounts.aliases))
def delete(alias):
    account = accounts.load(alias)
    if not isinstance(account, KeyfileAccount):
        click.echo(f"Account '{alias}' is not able to be deleted")
        return

    account.delete()
    click.echo(f"Account '{alias}' has been deleted")
