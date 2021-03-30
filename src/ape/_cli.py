from typing import Dict

import click
import yaml

from ape.plugins import clean_plugin_name, plugin_manager


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
    for module in installed_plugins:
        version_str = f" ({module.__version__})" if hasattr(module, "__version__") else ""
        click.echo(f"  {module.__name__}" + version_str)

    ctx.exit()  # NOTE: Must exit to bypass running ApeCLI


class ApeCLI(click.MultiCommand):
    _commands = None

    @property
    def commands(self) -> Dict:
        if self._commands is None:
            self._commands = {
                clean_plugin_name(impl.plugin_name): impl.plugin.cli_subcommand
                for impl in plugin_manager.hook.cli_subcommand.get_hookimpls()
            }

        return self._commands

    def list_commands(self, ctx):
        return list(sorted(self.commands))

    def get_command(self, ctx, name):
        if name in self.commands:
            return self.commands[name]()

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
