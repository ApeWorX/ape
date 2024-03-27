from pathlib import Path

import click
from click import BadArgumentUsage

from ape.cli.choices import _ACCOUNT_TYPE_FILTER, Alias
from ape.logging import logger
from ape.utils.basemodel import ManagerAccessMixin
from ape.utils.os import get_full_extension
from ape.utils.validators import _validate_account_alias


def _alias_callback(ctx, param, value):
    return _validate_account_alias(value)


def existing_alias_argument(account_type: _ACCOUNT_TYPE_FILTER = None, **kwargs):
    """
    A ``click.argument`` for an existing account alias.

    Args:
        account_type (Type[:class:`~ape.api.accounts.AccountAPI`], optional):
          If given, limits the type of account the user may choose from.
        **kwargs: click.argument overrides.
    """

    type_ = kwargs.pop("type", Alias(key=account_type))
    return click.argument("alias", type=type_, **kwargs)


def non_existing_alias_argument(**kwargs):
    """
    A ``click.argument`` for an account alias that does not yet exist in ape.

    Args:
        **kwargs: click.argument overrides.
    """

    callback = kwargs.pop("callback", _alias_callback)
    return click.argument("alias", callback=callback, **kwargs)


def _create_contracts_paths(ctx, param, value):
    pm = ctx.params.get("project", ManagerAccessMixin.project_manager)
    cm = ManagerAccessMixin.compiler_manager
    if value:
        paths = [Path(v) for v in value]
    else:
        return "*"  # Get all (after all config stuff sorted out).

    path_set = set()
    suffixed_warned = set()

    def lookup(path_ls):
        for path in path_ls:
            if (
                pm.path / path.name
            ) == pm.contracts_folder or path.name == pm.contracts_folder.name:
                # Was given the path to the contracts folder.
                lookup([p for p in pm.sources.paths])

            elif (pm.path / path).is_dir():
                # Was given sub-dir in the project folder.
                lookup([p for p in (pm.path / path).iterdir()])

            elif (pm.contracts_folder / path).is_dir():
                # Was given sub-dir in the contracts folder.
                lookup([p for p in (pm.contracts_folder / path).iterdir()])

            elif path.name.startswith("."):
                continue

            elif resolved_path := pm.sources.lookup(path):
                # Check compiler missing.
                suffix = get_full_extension(resolved_path)
                if (
                    suffix
                    and suffix not in cm.registered_compilers
                    and suffix not in suffixed_warned
                ):
                    # Warn for common missing compilers.
                    message = f"Missing compiler for '{suffix}' file extensions."
                    suffixed_warned.add(suffix)
                    if suffix == ".vy":
                        message = f"{message} Is 'ape-vyper' installed?"
                    elif suffix == ".sol":
                        message = f"{message} Is 'ape-solidity' installed?"
                    else:
                        continue

                    logger.error(message)
                    continue

                elif suffix in cm.registered_compilers:
                    # File exists and is compile-able.
                    path_set.add(resolved_path)

                elif suffix:
                    raise BadArgumentUsage(f"Source file '{resolved_path.name}' not found.")

            else:
                raise BadArgumentUsage(f"Source file '{path.name}' not found.")

    lookup(paths)

    return path_set


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
        callback=_create_contracts_paths,
    )
