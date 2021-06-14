from itertools import chain
from pathlib import Path

import click

from ape.utils import notify

flatten = chain.from_iterable


@click.command(short_help="Compile select contract source files")
@click.argument(
    "filepaths",
    nargs=-1,
    type=click.Path(exists=True, path_type=Path),
)
@click.option(
    "-f",
    "--force",
    "use_cache",
    flag_value=False,
    default=True,
    is_flag=True,
    help="Force recompiling selected contracts",
)
@click.option(
    "-s",
    "--size",
    "display_size",
    default=False,
    is_flag=True,
    help="Show deployment bytecode size for all contracts",
)
def cli(filepaths, use_cache, display_size):
    """
    Compiles the manifest for this project and saves the results
    back to the manifest.

    Note that ape automatically recompiles any changed contracts each time
    a project is loaded. You do not have to manually trigger a recompile.
    """
    # NOTE: Lazy load so that testing works properly
    from ape import project

    # Expand source tree based on selection
    if not filepaths:
        if not (project.path / "contracts").exists():
            notify("WARNING", "No `contracts/` directory detected")
            return

        # If no paths are specified, use all local project sources
        contract_filepaths = project.sources

    else:
        # Expand any folder paths
        expanded_filepaths = flatten([d.rglob("*.*") if d.is_dir() else [d] for d in filepaths])
        # Filter by what's in our project's source tree
        # NOTE: Make the paths absolute like `project.sources`
        contract_filepaths = [
            c.resolve() for c in expanded_filepaths if c.resolve() in project.sources
        ]

    if not contract_filepaths:
        if filepaths:
            selected_paths = "', '".join(str(p.resolve()) for p in filepaths)

        else:
            selected_paths = str(project.path / "contracts")

        notify("WARNING", f"No project files detected in '{selected_paths}'")
        return

    # TODO: only compile selected contracts
    contract_types = project.load_contracts(use_cache)

    # Display bytecode size for *all* contract types (not just ones we compiled)
    if display_size:
        codesize = []
        for contract in contract_types.values():
            if not contract.deploymentBytecode:
                continue  # Skip if not bytecode to display

            bytecode = contract.deploymentBytecode.bytecode

            if bytecode:
                codesize.append((contract.contractName, len(bytecode) // 2))

        if not codesize:
            notify("INFO", "No contracts with bytecode to display")
            return

        click.echo()
        click.echo("============ Deployment Bytecode Sizes ============")
        indent = max(len(i[0]) for i in codesize)
        for name, size in sorted(codesize, key=lambda k: k[1], reverse=True):
            pct = size / 24577
            # pct_color = color(next((i[1] for i in CODESIZE_COLORS if pct >= i[0]), ""))
            # TODO Get colors fixed for bytecode size output
            # click.echo(f"  {name:<{indent}}  -  {size:>6,}B  ({pct_color}{pct:.2%}{color})")
            click.echo(f"  {name:<{indent}}  -  {size:>6,}B  ({pct:.2%})")

        click.echo()
