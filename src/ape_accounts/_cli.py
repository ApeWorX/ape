import json

import click
from eth_account import Account as EthAccount  # type: ignore
from eth_utils import to_bytes

from ape import accounts
from ape.cli import ape_cli_context, existing_alias_argument, non_existing_alias_argument
from ape_accounts import KeyfileAccount


def _get_container():
    # NOTE: Must used the instantiated version of `AccountsContainer` in `accounts`
    return accounts.containers["accounts"]


@click.group(short_help="Manage local accounts")
def cli():
    """
    Command-line helper for managing local accounts. You can unlock local accounts from
    scripts or the console using the accounts.load() method.
    """


# Different name because `list` is a keyword
@cli.command(name="list", short_help="List available local accounts")
@click.option("--all", "show_all_plugins", help="Output accounts from all plugins", is_flag=True)
@ape_cli_context()
def _list(cli_ctx, show_all_plugins):
    if "accounts" not in accounts.containers:
        cli_ctx.abort("Accounts plugin unexpectedly failed to load.")

    containers = accounts.containers if show_all_plugins else {"accounts": _get_container()}
    account_map = {n: [a for a in c.accounts] for n, c in containers.items()}
    account_map = [pair for pair in {n: ls for n, ls in account_map.items() if len(ls) > 0}.items()]

    if sum([len(c) for c in account_map]) == 0:
        cli_ctx.logger.warning("No accounts found.")
        return

    num_containers = len(account_map)
    for index in range(num_containers):
        plugin_name, container = account_map[index]
        num_accounts = len(container)
        header = f"Found {num_accounts} account"
        if num_accounts > 1:
            header = f"{header}s"  # 'account' -> 'accounts'

        if show_all_plugins:
            header = f"{header} in the '{plugin_name}' plugin"

        click.echo(f"{header}:")

        for account in container:
            alias_display = f" (alias: '{account.alias}')" if account.alias else ""
            click.echo(f"  {account.address}{alias_display}")

        if index < num_containers - 1:
            click.echo()


@cli.command(short_help="Create a new keyfile account with a random private key")
@non_existing_alias_argument()
@ape_cli_context()
def generate(cli_ctx, alias):
    path = _get_container().data_folder.joinpath(f"{alias}.json")
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
    cli_ctx.logger.success(
        f"A new account '{account.address}' has been added with the id '{alias}'"
    )


# Different name because `import` is a keyword
@cli.command(name="import", short_help="Add a new keyfile account by entering a private key")
@non_existing_alias_argument()
@ape_cli_context()
def _import(cli_ctx, alias):
    path = _get_container().data_folder.joinpath(f"{alias}.json")
    key = click.prompt("Enter Private Key", hide_input=True)
    try:
        account = EthAccount.from_key(to_bytes(hexstr=key))
    except Exception as error:
        cli_ctx.abort(f"Key can't be imported: {error}")
        return

    passphrase = click.prompt(
        "Create Passphrase",
        hide_input=True,
        confirmation_prompt=True,
    )
    path.write_text(json.dumps(EthAccount.encrypt(account.key, passphrase)))
    cli_ctx.logger.success(
        f"A new account '{account.address}' has been added with the id '{alias}'"
    )


@cli.command(short_help="Change the password of an existing account")
@existing_alias_argument(account_type=KeyfileAccount)
@ape_cli_context()
def change_password(cli_ctx, alias):
    account = accounts.load(alias)
    account.change_password()
    cli_ctx.logger.success(f"Password has been changed for account '{alias}'")


@cli.command(short_help="Delete an existing account")
@existing_alias_argument(account_type=KeyfileAccount)
@ape_cli_context()
def delete(cli_ctx, alias):
    account = accounts.load(alias)
    account.delete()
    cli_ctx.logger.success(f"Account '{alias}' has been deleted")
