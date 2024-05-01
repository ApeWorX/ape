import json
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


# TODO: Delete for 0.8 (list of lists is weird and we
#  are no longer using this).
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

        if not path.is_file() and path.is_absolute():
            # Don't do absolute non-existent paths.
            # Let it resolve elsewhere.
            path = PathLibPath(value)

        return get_all_files_in_directory(path) if path.is_dir() else [path]


class JSON(click.ParamType):
    """
    A type that accepts a raw-JSON str
    and loads it into a dictionary.
    """

    def convert(self, value, param, ctx):
        if not value:
            return {}

        elif isinstance(value, str):
            try:
                return json.loads(value)
            except ValueError as err:
                self.fail(f"Invalid JSON string: {err}", param, ctx)

        return value  # Good already.
