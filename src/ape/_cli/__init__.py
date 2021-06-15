import click
import yaml
from ape_compile._cli import cli as compile
from ape_console._cli import cli as console
from ape_networks._cli import cli as networks
from ape_plugins._cli import cli as plugins

from ape._cli.groups import ApeCLI
from ape_accounts._cli import cli as accounts  # type: ignore


def display_config(ctx, param, value):
    # NOTE: This is necessary not to interrupt how version or help is intercepted
    if not value or ctx.resilient_parsing:
        return

    from ape import project

    click.echo("# Current configuration")
    click.echo(yaml.dump(project.config.serialize()))

    ctx.exit()  # NOTE: Must exit to bypass running ApeCLI

CONTEXT_SETTINGS = {
    "help_option_names": ["-h", "--help"],
    "max_content_width": 200,
}
config_option = click.option(
    "--config",
    is_flag=True,
    is_eager=True,
    expose_value=False,
    callback=display_config,
    help="Show configuration options (using `ape-config.yaml`)",
)
version_option = click.version_option(message="%(version)s", package_name="eth-ape")


@click.group(
    cls=ApeCLI,
    context_settings=CONTEXT_SETTINGS,
    invoke_without_command=True,
    no_args_is_help=True,
)
@config_option
@version_option
def cli():
    ...


cli.add_command(accounts)  # type: ignore
cli.add_command(compile)  # type: ignore
cli.add_command(console)  # type: ignore
cli.add_command(plugins)  # type: ignore
cli.add_command(networks)  # type: ignore
