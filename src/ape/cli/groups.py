import click

from ape.cli.commands import NetworkBoundCommand


def ape_group(*args, **kwargs):
    return click.group(cls=ApeGroup, *args, **kwargs)


class ApeGroup(click.Group):
    def network_bound_command(self, *args, **kwargs):
        return self.command(cls=NetworkBoundCommand, *args, **kwargs)
