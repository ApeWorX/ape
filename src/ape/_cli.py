import click
import yaml

from ape.plugins import CliPlugin, registered_plugins

CLI_PLUGINS = {p.name: p for p in registered_plugins[CliPlugin]}


def display_config(ctx, param, value):
    # NOTE: This is necessary not to interrupt how version or help is intercepted
    if not value or ctx.resilient_parsing:
        return

    from ape import project

    click.echo("# Current configuration")
    click.echo(yaml.dump(project.config.serialize()))

    ctx.exit()  # NOTE: Must exit to bypass running ApeCLI


def display_plugins(ctx, param, value):
    # NOTE: This is necessary not to interrupt how version or help is intercepted
    if not value or ctx.resilient_parsing:
        return

    from ape import __discovered_plugins as installed_plugins

    click.echo("Installed plugins:")
    for module in installed_plugins.values():
        version_str = f" ({module.__version__})" if hasattr(module, "__version__") else ""
        click.echo(f"  {module.__name__}" + version_str)

    ctx.exit()  # NOTE: Must exit to bypass running ApeCLI


class ApeCLI(click.MultiCommand):
    def list_commands(self, ctx):
        return list(sorted(CLI_PLUGINS.keys()))

    def get_command(self, ctx, name):
        if name in CLI_PLUGINS:
            return CLI_PLUGINS[name].data

        # NOTE: don't return anything so Click displays proper error


@click.command(cls=ApeCLI, context_settings=dict(help_option_names=["-h", "--help"]))
@click.version_option(message="%(version)s")
@click.option(
    "--config",
    is_flag=True,
    is_eager=True,
    expose_value=False,
    callback=display_config,
)
@click.option(
    "--plugins",
    is_flag=True,
    is_eager=True,
    expose_value=False,
    callback=display_plugins,
)
def cli():
    pass
