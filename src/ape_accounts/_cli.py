import json

import click
from eth_account import Account as EthAccount
from eth_account.hdaccount import ETHEREUM_DEFAULT_PATH
from eth_utils import to_bytes

from ape import accounts
from ape.cli import ape_cli_context, existing_alias_argument, non_existing_alias_argument
from ape_accounts import AccountContainer, KeyfileAccount


def _get_container() -> AccountContainer:
    # NOTE: Must used the instantiated version of `AccountsContainer` in `accounts`
    container = accounts.containers["accounts"]
    assert isinstance(container, AccountContainer)
    return container


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
    account_pairs = [
        pair for pair in {n: ls for n, ls in account_map.items() if len(ls) > 0}.items()
    ]

    if sum(len(c) for c in account_pairs) == 0:
        cli_ctx.logger.warning("No accounts found.")
        return

    num_containers = len(account_pairs)
    for index in range(num_containers):
        plugin_name, container = account_pairs[index]
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


@cli.command(short_help="Create an account with a random mnemonic seed phrase")
@click.option(
    "--hide-mnemonic",
    help="Hide the newly generated mnemonic from the terminal",
    is_flag=True,
)
@click.option(
    "--word-count",
    help="Number of words to use to generate seed phrase",
    default=12,
    show_default=True,
)
@click.option(
    "--hd-path",
    "custom_hd_path",
    help="Specify an HD path for deriving seed phrase",
    default=ETHEREUM_DEFAULT_PATH,
    show_default=True,
)
@non_existing_alias_argument()
@ape_cli_context()
def generate(cli_ctx, alias, hide_mnemonic, word_count, custom_hd_path):
    path = _get_container().data_folder.joinpath(f"{alias}.json")
    EthAccount.enable_unaudited_hdwallet_features()
    # os.urandom (used internally for this method) requries a certain amount of entropy
    # Adding entropy increases os.urandom randomness output
    # Despite not being used in create_with_mnemonic
    click.prompt(
        "Add extra entropy for key generation...",
        hide_input=True,
    )
    account, mnemonic = EthAccount.create_with_mnemonic(
        num_words=word_count, account_path=custom_hd_path
    )
    if not hide_mnemonic and click.confirm("Show mnemonic?", default=True):
        cli_ctx.logger.info(f"Newly generated mnemonic is: {click.style(mnemonic, bold=True)}")
    passphrase = click.prompt(
        "Create Passphrase to encrypt account",
        hide_input=True,
        confirmation_prompt=True,
    )
    path.write_text(json.dumps(EthAccount.encrypt(account.key, passphrase)))
    cli_ctx.logger.success(
        f"A new account '{account.address}' with "
        + f"HDPath {custom_hd_path} has been added with the id '{alias}'"
    )


# Different name because `import` is a keyword
@cli.command(name="import", short_help="Import an account by private key or seed phrase")
@click.option(
    "--use-mnemonic", "import_from_mnemonic", help="Import a key from a mnemonic", is_flag=True
)
@click.option(
    "--hd-path",
    "custom_hd_path",
    help="Account HD path to use when importing by mnemonic",
    default=ETHEREUM_DEFAULT_PATH,
    show_default=True,
)
@non_existing_alias_argument()
@ape_cli_context()
def _import(cli_ctx, alias, import_from_mnemonic, custom_hd_path):
    path = _get_container().data_folder.joinpath(f"{alias}.json")
    if import_from_mnemonic:
        mnemonic = click.prompt("Enter mnemonic seed phrase", hide_input=True)
        EthAccount.enable_unaudited_hdwallet_features()
        try:
            account = EthAccount.from_mnemonic(mnemonic=mnemonic, account_path=custom_hd_path)
        except Exception as error:
            cli_ctx.abort(f"Seed phrase can't be imported: {error}")

    else:
        key = click.prompt("Enter Private Key", hide_input=True)
        try:
            account = EthAccount.from_key(to_bytes(hexstr=key))
        except Exception as error:
            cli_ctx.abort(f"Key can't be imported: {error}")

    passphrase = click.prompt(
        "Create Passphrase to encrypt account",
        hide_input=True,
        confirmation_prompt=True,
    )
    path.write_text(json.dumps(EthAccount.encrypt(account.key, passphrase)))
    cli_ctx.logger.success(
        f"A new account '{account.address}' has been added with the id '{alias}'"
    )


@cli.command(short_help="Export an account private key")
@ape_cli_context()
@existing_alias_argument(account_type=KeyfileAccount)
def export(cli_ctx, alias):
    path = _get_container().data_folder.joinpath(f"{alias}.json")
    account = json.loads(path.read_text())
    password = click.prompt("Enter password to decrypt account", hide_input=True)
    private_key = EthAccount.decrypt(account, password)
    cli_ctx.logger.success(
        f"Account 0x{account['address']} private key: {click.style(private_key.hex(), bold=True)})"
    )


@cli.command(short_help="Change the password of an existing account")
@existing_alias_argument(account_type=KeyfileAccount)
@ape_cli_context()
def change_password(cli_ctx, alias):
    account = accounts.load(alias)
    assert isinstance(account, KeyfileAccount)
    account.change_password()
    cli_ctx.logger.success(f"Password has been changed for account '{alias}'")


@cli.command(short_help="Delete an existing account")
@existing_alias_argument(account_type=KeyfileAccount)
@ape_cli_context()
def delete(cli_ctx, alias):
    account = accounts.load(alias)
    assert isinstance(account, KeyfileAccount)
    account.delete()
    cli_ctx.logger.success(f"Account '{alias}' has been deleted")
