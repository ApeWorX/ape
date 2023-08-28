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
        if "path_type" not in kwargs:
            kwargs["path_type"] = PathLibPath

        super().__init__(*args, **kwargs)


class AllFilePaths(Path):
    """
    Either all the file paths in the given directory,
    or a list containing only the given file.
    """

    def convert(  # type: ignore[override]
        self, value: Any, param: Optional["Parameter"], ctx: Optional["Context"]
    ) -> List[PathLibPath]:
        path = super().convert(value, param, ctx)
        assert isinstance(path, PathLibPath)  # For mypy
        return get_all_files_in_directory(path) if path.is_dir() else [path]
