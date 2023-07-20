from itertools import chain
from typing import Optional, Type

import click
from eth_utils import is_hex

from ape import accounts, project
from ape.api import AccountAPI
from ape.cli.choices import Alias
from ape.cli.paramtype import AllFilePaths
from ape.exceptions import AccountsError, AliasAlreadyInUseError

_flatten = chain.from_iterable


def _alias_callback(ctx, param, value):
    if value in accounts.aliases:
        # Alias cannot be used.
        raise AliasAlreadyInUseError(value)

    elif not isinstance(value, str):
        raise AccountsError(f"Alias must be a str, not '{type(value)}'.")
    elif is_hex(value) and len(value) >= 42:
        raise AccountsError("Longer aliases cannot be hex strings.")

    return value


def existing_alias_argument(account_type: Optional[Type[AccountAPI]] = None):
    """
    A ``click.argument`` for an existing account alias.

    Args:
        account_type (Type[:class:`~ape.api.accounts.AccountAPI`], optional):
          If given, limits the type of account the user may choose from.
    """

    return click.argument("alias", type=Alias(account_type=account_type))


def non_existing_alias_argument():
    """
    A ``click.argument`` for an account alias that does not yet exist in ape.
    """

    return click.argument("alias", callback=_alias_callback)


def _create_contracts_paths(ctx, param, value):
    contract_paths = _flatten(value)

    def _raise_bad_arg(name):
        raise click.BadArgumentUsage(f"Contract '{name}' not found.")

    resolved_contract_paths = set()
    for contract_path in contract_paths:
        # Adds missing absolute path as well as extension.
        pm = project if ctx.obj is None else ctx.obj.project_manager
        resolved_contract_path = pm.lookup_path(contract_path)
        if not resolved_contract_path:
            _raise_bad_arg(contract_path.name)

        resolved_contract_paths.add(resolved_contract_path)

    return resolved_contract_paths


def contract_file_paths_argument():
    """
    A ``click.argument`` representing contract source file paths.
    This argument takes 0-to-many values.

    The return type from the callback is a flattened list of
    source file-paths.
    """

    return click.argument(
        "file_paths",
        nargs=-1,
        type=AllFilePaths(resolve_path=True),
        callback=_create_contracts_paths,
    )
