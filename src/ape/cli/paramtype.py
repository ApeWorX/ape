from pathlib import Path as PathLibPath
from typing import Any, List, Optional

import click
from click import Context, Parameter

from ape.utils import get_all_files_in_directory


class Path(click.Path):
    """
    This class exists to encourage the consistent usage
    of ``pathlib.Path`` for path_type.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, path_type=PathLibPath, **kwargs)


class AllFilePaths(Path):
    """
    Either all the file paths in the given directory,
    or a list containing only the given file.
    """

    def convert(
        self, value: Any, param: Optional["Parameter"], ctx: Optional["Context"]
    ) -> List[PathLibPath]:
        path = super().convert(value, param, ctx)

        # NOTE: Return the path if it does not exist so it can be resolved downstream.
        return get_all_files_in_directory(path) if path.exists() else [path]
