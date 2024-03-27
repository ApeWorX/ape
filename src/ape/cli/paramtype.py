import json
from pathlib import Path as PathLibPath

import click


class Path(click.Path):
    """
    This class exists to encourage the consistent usage
    of ``pathlib.Path`` for path_type.
    """

    def __init__(self, *args, **kwargs):
        if "path_type" not in kwargs:
            kwargs["path_type"] = PathLibPath

        super().__init__(*args, **kwargs)


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
