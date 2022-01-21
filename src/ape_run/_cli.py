import click

from ape.cli import NetworkBoundCommand, ape_cli_context, network_option


@click.command(cls=NetworkBoundCommand, short_help="Run scripts from the `scripts` folder")
@click.argument("scripts", nargs=-1)
@click.option(
    "-i",
    "--interactive",
    is_flag=True,
    default=False,
    help="Drop into interactive console session after running",
)
@ape_cli_context()
@network_option()
def cli(cli_ctx, scripts, interactive, network):
    """
    NAME - Path or script name (from ``scripts/`` folder)

    Run scripts from the ``scripts`` folder. A script must either define a ``main()`` method,
    or define an import named ``cli`` that is a ``click.Command`` or ``click.Group`` object.
    ``click.Group`` and ``click.Command`` objects will be provided with additional context, which
    will be injected dynamically during script execution. The dynamically injected objects are
    the exports from the ``ape`` top-level package (similar to how the console works)
    """
    _ = network  # Not used directly but required.

    if not scripts:
        cli_ctx.abort("Must provide at least one script name or path.")

    for name in scripts:
        cli_ctx.project.run_script(name, interactive)
