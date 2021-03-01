import shutil

import click

from ape.compilers import load


@click.command(short_help="Compile the contract source files")
@click.argument("contracts", type=str, nargs=-1)
@click.option(
    "-a", "--all", "compile_all", default=False, is_flag=True, help="Recompile all contracts"
)
@click.option(
    "-s",
    "--size",
    "display_size",
    default=False,
    is_flag=True,
    help="Show deployed bytecode sizes contracts",
)
def cli(contracts, compile_all, display_size):
    """
    Compiles the contract source files for this project and saves the results
    in the build/contracts/ folder.

    An optional list of specific CONTRACTS can be provided.

    Note that ape automatically recompiles any changed contracts each time
    a project is loaded. You do not have to manually trigger a recompile.
    """
    click.echo("loading compiler plugin to handle .vy files")
    compiler = load(".vy")
    click.echo(f"loaded {compiler.name} compiler, compiling")
    compiler.compile("/path/to/contracts/")
