import click

from ape.plugins import CliPlugin, registered_plugins

CLI_PLUGINS = {p.name: p for p in registered_plugins[CliPlugin]}


class ApeCLI(click.MultiCommand):
    def list_commands(self, ctx):
        return list(sorted(CLI_PLUGINS.keys()))

    def get_command(self, ctx, name):
        if name in CLI_PLUGINS:
            return CLI_PLUGINS[name].data

        # NOTE: don't return anything so Click displays proper error


@click.command(cls=ApeCLI, context_settings=dict(help_option_names=["-h", "--help"]))
@click.version_option(message="%(version)s")
def cli():
    pass
