from typing import Dict

import click
from ethpm_types import ContractType

from ape.cli import ape_cli_context, contract_file_paths_argument


@click.command(short_help="Compile select contract source files")
@contract_file_paths_argument()
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
@ape_cli_context()
def cli(cli_ctx, file_paths, use_cache, display_size):
    """
    Compiles the manifest for this project and saves the results
    back to the manifest.

    Note that ape automatically recompiles any changed contracts each time
    a project is loaded. You do not have to manually trigger a recompile.
    """

    if not file_paths and cli_ctx.project_manager.sources_missing:
        contracts_dir = cli_ctx.config_manager.contracts_folder
        cli_ctx.logger.warning(f"No source files found in '{contracts_dir}'.")
        return

    ext_given = [p.suffix for p in file_paths if p]
    ext_with_missing_compilers = cli_ctx.project_manager.extensions_with_missing_compilers(
        ext_given
    )

    if ext_with_missing_compilers:
        extensions_str = ", ".join(ext_with_missing_compilers)
        message = f"No compilers detected for the following extensions: {extensions_str}"
        cli_ctx.logger.warning(message)

    contract_types = cli_ctx.project_manager.load_contracts(
        file_paths=file_paths, use_cache=use_cache
    )

    if display_size:
        _display_byte_code_sizes(cli_ctx, contract_types)


def _display_byte_code_sizes(cli_ctx, contract_types: Dict[str, ContractType]):
    # Display bytecode size for *all* contract types (not just ones we compiled)
    code_size = []
    for contract in contract_types.values():
        if not contract.deployment_bytecode:
            continue  # Skip if not bytecode to display

        bytecode = contract.deployment_bytecode.bytecode

        if bytecode:
            code_size.append((contract.name, len(bytecode) // 2))

    if not code_size:
        cli_ctx.logger.info("No contracts with bytecode to display")
        return

    click.echo()
    click.echo("============ Deployment Bytecode Sizes ============")
    indent = max(len(i[0]) for i in code_size)  # type: ignore
    for name, size in sorted(code_size, key=lambda k: k[1], reverse=True):
        pct = size / 24577
        # pct_color = color(next((i[1] for i in CODESIZE_COLORS if pct >= i[0]), ""))
        # TODO Get colors fixed for bytecode size output
        # click.echo(f"  {name:<{indent}}  -  {size:>6,}B  ({pct_color}{pct:.2%}{color})")
        click.echo(f"  {name:<{indent}}  -  {size:>6,}B  ({pct:.2%})")

    click.echo()
