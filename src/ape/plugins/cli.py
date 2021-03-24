from typing import Union

import click

from .pluggy import hookspec


class CliPlugin:
    @hookspec
    def cli_subcommand(self) -> Union[click.Command, click.Group]:
        """
        Register a subcommand to be added to the ape interface
        """
