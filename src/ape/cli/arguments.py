from itertools import chain
from typing import Optional, Type

import click

from ape import accounts
from ape.api import AccountAPI
from ape.cli.choices import Alias
from ape.cli.paramtype import AllFilePaths
from ape.exceptions import AliasAlreadyInUseError

_flatten = chain.from_iterable


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


def _create_contracts_paths(ctx, param, value):
    contract_paths = _flatten(value)

    def _raise_bad_arg(name):
        raise click.BadArgumentUsage(f"Contract '{name}' not found.")

    resolved_contract_paths = set()
    for contract_path in contract_paths:
        # Adds missing absolute path as well as extension.
        resolved_contract_path = ctx.obj.project.lookup_path(contract_path)

        if not resolved_contract_path:
            _raise_bad_arg(contract_path.name)

        resolved_contract_paths.add(resolved_contract_path)

    return resolved_contract_paths


def contract_file_paths_argument():
    return click.argument(
        "file_paths",
        nargs=-1,
        type=AllFilePaths(resolve_path=True),
        callback=_create_contracts_paths,
    )
