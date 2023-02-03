import click


@click.command(short_help="Use a subcommand")
def cli():
    local_variable = "test foo bar"
    raise Exception(f"Expected exception - {local_variable}")  # noqa: T001
