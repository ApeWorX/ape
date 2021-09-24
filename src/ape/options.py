from typing import List, Optional, Type

import click

from ape import accounts, networks
from ape.api.accounts import AccountAPI
from ape.exceptions import AliasAlreadyInUseError


class NetworkChoice(click.Choice):
    """Wraps ``click.Choice`` to provide network choice defaults for the active project."""

    def __init__(self, case_sensitive=True):
        super().__init__(list(networks.network_choices), case_sensitive)

    def get_metavar(self, param):
        return "[ecosystem-name][:[network-name][:[provider-name]]]"


network_option = click.option(
    "--network",
    type=NetworkChoice(case_sensitive=False),
    default=networks.default_ecosystem.name,
    help="Override the default network and provider. (see ``ape networks list`` for options)",
    show_default=True,
    show_choices=False,
)


def verbose_option(help=""):
    return click.option(
        "-v",
        "--verbose",
        is_flag=True,
        default=False,
        help=help,
    )


class Alias(click.Choice):
    """Wraps ``click.Choice`` to load account aliases for the active project at runtime.

    Provide an ``account_type`` to limit the type of account to choose from.
    Defaults to all account types in ``choices()``.
    """

    name = "alias"

    def __init__(self, account_type: Optional[Type[AccountAPI]] = None):
        # NOTE: we purposely skip the constructor of `Choice`
        self.case_sensitive = False
        self._account_type = account_type

    @property
    def choices(self) -> List[str]:  # type: ignore
        options = (
            list(accounts)
            if not self._account_type
            else accounts.get_accounts_by_type(self._account_type)
        )
        return [a.alias for a in options if a.alias is not None]


def _require_non_existing_alias(arg):
    if arg in accounts.aliases:
        raise AliasAlreadyInUseError(arg)
    return arg


def existing_alias_argument(account_type: Optional[Type[AccountAPI]] = None):
    return click.argument("alias", type=Alias(account_type=account_type))


non_existing_alias_argument = click.argument(
    "alias", callback=lambda ctx, param, arg: _require_non_existing_alias(arg)
)
