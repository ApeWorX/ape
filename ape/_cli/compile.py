import os
import shutil

from ape.compilers import load
from ape.utils import notify

import click


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

    if len(contracts) == 0:
        notify("ERROR", "No contracts argument provided")
        return

    for p in contracts:
        extensions = {
            os.path.splitext(c)[1] for c in os.listdir(p) if not os.path.splitext(c)[1] == ""
        }
        for c in extensions:
            try:
                compiler = load(c)
            except IndexError:
                click.echo(f"No compiler found for '{c}'")
                click.echo()
                continue

            click.echo(f"{compiler.name} loaded to handle '{c}' contracts")
            result = compiler.compile(p)

            if display_size:
                click.echo()
                click.echo("============ Deployment Bytecode Sizes ============")
                codesize = []
                for contract in result.keys():
                    if contract == "version":
                        continue
                    bytecode = result[contract]["bytecode"]
                    if bytecode:
                        codesize.append((contract, len(bytecode) // 2))
                indent = max(len(i[0]) for i in codesize)
                for name, size in sorted(codesize, key=lambda k: k[1], reverse=True):
                    pct = size / 24577
                    # pct_color = color(next((i[1] for i in CODESIZE_COLORS if pct >= i[0]), ""))
                    # TODO Get colors fixed for bytecode size output
                    # click.echo(f"  {name:<{indent}}  -  {size:>6,}B  ({pct_color}{pct:.2%}{color})")
                    click.echo(f"  {name:<{indent}}  -  {size:>6,}B  ({pct:.2%})")
                click.echo()
