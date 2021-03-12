import click


@click.command(short_help="Compile the contract source files")
@click.argument("contracts", nargs=-1, type=click.Path())
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
    Note that Ape automatically recompiles any changed contracts each time
    a project is loaded. You do not have to manually trigger a recompile."""
