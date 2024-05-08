from fnmatch import fnmatch
from functools import cached_property
from pathlib import Path
from typing import Iterable, List, Set, Union

import click
from click import BadArgumentUsage

from ape.cli.choices import _ACCOUNT_TYPE_FILTER, Alias
from ape.logging import logger
from ape.utils.basemodel import ManagerAccessMixin
from ape.utils.os import get_all_files_in_directory, get_full_extension
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


class _ContractPaths(ManagerAccessMixin):
    """
    Helper callback class for handling CLI-given contract paths.
    """

    def __init__(self, value):
        self.value = value
        self._path_set = set()
        self.missing_compilers = set()
        self.exclude_list = {}

    @classmethod
    def callback(cls, ctx, param, value) -> Set[Path]:
        """
        Use this for click.option / argument callbacks.
        """
        return cls(value).filtered_paths

    @cached_property
    def filtered_paths(self) -> Set[Path]:
        """
        Get the filtered set of paths.
        """
        value = self.value
        contract_paths: Iterable[Path]

        if value and isinstance(value, (list, tuple, set)):
            # Given a single list of paths.
            contract_paths = value

        elif value and isinstance(value, (Path, str)):
            # Given single path.
            contract_paths = (Path(value),)

        elif not value or value == "*":
            # Get all file paths in the project.
            contract_paths = get_all_files_in_directory(self.project_manager.contracts_folder)

        else:
            raise ValueError(f"Unknown contracts-paths value '{value}'.")

        self.lookup(contract_paths)

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

        return self._path_set

    @property
    def exclude_patterns(self) -> List[str]:
        return self.config_manager.get_config("compile").exclude or []

    def do_exclude(self, path: Union[Path, str]) -> bool:
        name = path if isinstance(path, str) else str(path)
        if name not in self.exclude_list:
            self.exclude_list[name] = any(fnmatch(name, p) for p in self.exclude_patterns)

        return self.exclude_list[name]

    def compiler_is_unknown(self, path: Union[Path, str]) -> bool:
        path = Path(path)
        if self.do_exclude(path):
            return False

        ext = get_full_extension(path)
        unknown_compiler = ext and ext not in self.compiler_manager.registered_compilers
        if unknown_compiler and ext not in self.missing_compilers:
            self.missing_compilers.add(ext)

        return bool(unknown_compiler)

    def lookup(self, path_iter):
        for path in path_iter:
            path = Path(path)
            if self.do_exclude(path):
                continue

            contracts_folder = self.project_manager.contracts_folder
            if (
                self.project_manager.path / path.name
            ) == contracts_folder or path.name == contracts_folder.name:
                # Was given the path to the contracts folder.
                self.lookup(p for p in self.project_manager.source_paths)

            elif (self.project_manager.path / path).is_dir():
                # Was given sub-dir in the project folder.
                self.lookup(p for p in (self.project_manager.path / path).iterdir())

            elif (contracts_folder / path.name).is_dir():
                # Was given sub-dir in the contracts folder.
                self.lookup(p for p in (contracts_folder / path.name).iterdir())

            elif resolved_path := self.project_manager.lookup_path(path):
                # Check compiler missing.
                if self.compiler_is_unknown(resolved_path):
                    # NOTE: ^ Also tracks.
                    continue

                suffix = get_full_extension(resolved_path)
                if suffix in self.compiler_manager.registered_compilers:
                    # File exists and is compile-able.
                    self._path_set.add(resolved_path)

                elif suffix:
                    raise BadArgumentUsage(f"Source file '{resolved_path.name}' not found.")

            else:
                raise BadArgumentUsage(f"Source file '{path.name}' not found.")


def contract_file_paths_argument():
    """
    A ``click.argument`` representing contract source file paths.
    This argument takes 0-to-many values.

    The return type from the callback is a flattened list of
    source file-paths.
    """
    return click.argument("file_paths", nargs=-1, callback=_ContractPaths.callback)
