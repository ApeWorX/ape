from typing import Optional, Type

import click

from ape import accounts
from ape.api import AccountAPI
from ape.cli.choices import Alias
from ape.exceptions import AliasAlreadyInUseError


def _require_non_existing_alias(value):
    if value in accounts.aliases:
        raise AliasAlreadyInUseError(value)
    return value


def existing_alias_argument(account_type: Optional[Type[AccountAPI]] = None):
    return click.argument("alias", type=Alias(account_type=account_type))


def non_existing_alias_argument():
    return click.argument(
        "alias", callback=lambda ctx, param, value: _require_non_existing_alias(value)
    )
