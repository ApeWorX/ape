from pathlib import Path
from typing import Dict, Set

import click
from ethpm_types import ContractType

from ape.cli import ape_cli_context, config_override_option, contract_file_paths_argument


def _include_dependencies_callback(ctx, param, value):
    return value or ctx.obj.config_manager.get_config("compile").include_dependencies


def _config_override_callback(ctx, param, value):
    if value:
        ctx.obj.config_manager.load(force_reload=True, **value)


@click.command(short_help="Compile select contract source files")
@ape_cli_context()
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
@click.option(
    "--include-dependencies",
    is_flag=True,
    help="Also compile dependencies",
    callback=_include_dependencies_callback,
)
@config_override_option(callback=_config_override_callback)
def cli(
    cli_ctx,
    file_paths: Set[Path],
    use_cache: bool,
    display_size: bool,
    include_dependencies,
    config_override,
):
    """
    Compiles the manifest for this project and saves the results
    back to the manifest.

    Note that ape automatically recompiles any changed contracts each time
    a project is loaded. You do not have to manually trigger a recompile.
    """
    sources_missing = cli_ctx.project_manager.sources_missing
    if not file_paths and sources_missing and len(cli_ctx.project_manager.dependencies) == 0:
        cli_ctx.logger.warning("Nothing to compile.")
        return

    contract_types = cli_ctx.project_manager.load_contracts(
        file_paths=file_paths, use_cache=use_cache
    )

    if include_dependencies:
        for versions in cli_ctx.project_manager.dependencies.values():
            for dependency in versions.values():
                try:
                    dependency.compile(use_cache=use_cache)
                except Exception as err:
                    # Log error and try to compile the remaining dependencies.
                    cli_ctx.logger.error(err)

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
