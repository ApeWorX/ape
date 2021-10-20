from pathlib import Path as PathLibPath
from typing import Any, List, Optional

import click
from click import Context, Parameter


class Path(click.Path):
    """
    This class exists to encourage the consistent usage
    of ``pathlib.Path`` for path_type.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(path_type=PathLibPath)


class AllFilePaths(Path):
    """
    Either all the file paths in the given directory,
    or a list containing only the given file.
    """

    def convert(
        self, value: Any, param: Optional["Parameter"], ctx: Optional["Context"]
    ) -> List[PathLibPath]:
        path = super().convert(value, param, ctx)
        if path.is_dir():
            return list(path.rglob("*.*"))

        return [path]
