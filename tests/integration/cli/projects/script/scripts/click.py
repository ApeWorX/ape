import click


@click.command(short_help="Use a subcommand")
def cli():
    print("Super secret script output")  # noqa: T001
