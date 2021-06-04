import click
import yaml


def display_config(ctx, param, value):
    # NOTE: This is necessary not to interrupt how version or help is intercepted
    if not value or ctx.resilient_parsing:
        return

    from ape import project

    click.echo("# Current configuration")
    click.echo(yaml.dump(project.config.serialize()))

    ctx.exit()  # NOTE: Must exit to bypass running ApeCLI


config_option = click.option(
    "--config",
    is_flag=True,
    is_eager=True,
    expose_value=False,
    callback=display_config,
    help="Show configuration options (using `ape-config.yaml`)",
)
version_option = click.version_option(message="%(version)s", package_name="eth-ape")


def shared_options():
    """
    Shared options for every command.
    """

    def decorator(f):
        f = config_option(f)
        f = version_option(f)
        return f

    return decorator
