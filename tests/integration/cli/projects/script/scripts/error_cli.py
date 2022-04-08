import click


@click.command(short_help="Use a subcommand")
def cli():
    raise Exception("Expected exception")  # noqa: T001
