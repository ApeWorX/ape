from collections.abc import Iterable
from pathlib import Path
from typing import TYPE_CHECKING, Optional, Union

import click
from click import BadArgumentUsage

from ape.cli.choices import _ACCOUNT_TYPE_FILTER, Alias
from ape.logging import logger
from ape.utils.basemodel import ManagerAccessMixin
from ape.utils.os import get_full_extension
from ape.utils.validators import _validate_account_alias

if TYPE_CHECKING:
    from ape.managers.project import ProjectManager


def _alias_callback(ctx, param, value):
    return _validate_account_alias(value)


def existing_alias_argument(account_type: _ACCOUNT_TYPE_FILTER = None, **kwargs):
    """
    A ``click.argument`` for an existing account alias.

    Args:
        account_type (type[:class:`~ape.api.accounts.AccountAPI`], optional):
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


class _ContractPaths(ManagerAccessMixin):
    """
    Helper callback class for handling CLI-given contract paths.
    """

    def __init__(self, value, project: Optional["ProjectManager"] = None):
        self.value = value
        self.missing_compilers: set[str] = set()  # set of .ext
        self.project = project or ManagerAccessMixin.local_project

    @classmethod
    def callback(cls, ctx, param, value) -> set[Path]:
        """
        Use this for click.option / argument callbacks.
        """
        project = ctx.params.get("project")
        return cls(value, project=project).filtered_paths

    @property
    def filtered_paths(self) -> set[Path]:
        """
        Get the filtered set of paths.
        """
        value = self.value
        contract_paths: Iterable[Path]

        if value and isinstance(value, (Path, str)):
            # Given single path.
            contract_paths = (Path(value),)
        elif not value or value == "*":
            # Get all file paths in the project.
            return {p for p in self.project.sources.paths}
        elif isinstance(value, Iterable):
            contract_paths = value
        else:
            raise BadArgumentUsage(f"Not a path or iter[Path]: {value}")

        # Convert source IDs or relative paths to absolute paths.
        path_set = self.lookup(contract_paths)

        # Handle missing compilers.
        if self.missing_compilers:
            # Craft a nice message for all missing compilers.
            missing_ext = ", ".join(sorted(self.missing_compilers))
            message = (
                f"Missing compilers for the following file types: '{missing_ext}'. "
                "Possibly, a compiler plugin is not installed or is "
                "installed but not loading correctly."
            )
            if ".vy" in self.missing_compilers:
                message = f"{message} Is 'ape-vyper' installed?"
            if ".sol" in self.missing_compilers:
                message = f"{message} Is 'ape-solidity' installed?"

            logger.warning(message)

        return path_set

    @property
    def exclude_patterns(self) -> set[str]:
        return self.config_manager.get_config("compile").exclude or set()

    def do_exclude(self, path: Union[Path, str]) -> bool:
        return self.project.sources.is_excluded(path)

    def compiler_is_unknown(self, path: Union[Path, str]) -> bool:
        ext = get_full_extension(path)
        unknown_compiler = ext and ext not in self.compiler_manager.registered_compilers
        if unknown_compiler and ext not in self.missing_compilers:
            self.missing_compilers.add(ext)

        return bool(unknown_compiler)

    def lookup(self, path_iter: Iterable, path_set: Optional[set] = None) -> set[Path]:
        path_set = path_set or set()
        given_paths = [p for p in path_iter]  # Handle iterators w/o losing it.

        for path_id in given_paths:
            path = Path(path_id)
            contracts_folder = self.project.contracts_folder
            if (
                self.project.path / path.name
            ) == contracts_folder or path.name == contracts_folder.name:
                # Was given the path to the contracts folder.
                path_set = path_set.union({p for p in self.project.sources.paths})

            elif (self.project.path / path).is_dir():
                # Was given sub-dir in the project folder.
                path_set = path_set.union(
                    self.lookup(
                        (p for p in (self.project.path / path).iterdir()), path_set=path_set
                    )
                )

            elif (contracts_folder / path.name).is_dir():
                # Was given sub-dir in the contracts folder.
                path_set = path_set.union(
                    self.lookup(
                        (p for p in (contracts_folder / path.name).iterdir()), path_set=path_set
                    )
                )

            elif resolved_path := self.project.sources.lookup(path):
                # Check compiler missing.
                if self.compiler_is_unknown(resolved_path):
                    # NOTE: ^ Also tracks.
                    continue

                # We know here that the compiler is known.
                path_set.add(resolved_path)

            else:
                raise BadArgumentUsage(f"Source file '{path.name}' not found.")

        return path_set


def contract_file_paths_argument():
    """
    A ``click.argument`` representing contract source file paths.
    This argument takes 0-to-many values.

    The return type from the callback is a flattened list of
    source file-paths.
    """
    return click.argument("file_paths", nargs=-1, callback=_ContractPaths.callback)
