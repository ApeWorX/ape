import click


@click.command()
def cli():
    click.echo("Super secret script output")  # noqa: T001
