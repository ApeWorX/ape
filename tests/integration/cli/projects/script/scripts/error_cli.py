import click

import ape


@click.command(short_help="Use a subcommand")
def cli():
    local_variable = "test foo bar"  # noqa[F841]
    provider = ape.chain.provider
    provider.set_timestamp(123123123123123123)
    raise Exception("Expected exception")  # noqa: T001
