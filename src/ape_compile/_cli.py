from itertools import chain
from pathlib import Path
from typing import Dict, List, Optional

import click

from ape.cli import ape_cli_context
from ape.types import ContractType

flatten = chain.from_iterable


class _ContractsSource:
    """
    A helper class that is able to figure out which source files to
    compile.
    """

    def __init__(self, use_cache: bool):
        # NOTE: Lazy load so that testing works properly
        from ape import project

        self._project = project
        self._use_cache = use_cache

    @property
    def root(self) -> Path:
        return self._project.path / "contracts"

    def select_paths(self, file_paths: Optional[List[Path]]):
        # If not given sources, assume user wants to compile all source files.
        # Excludes files without registered compilers.
        if not file_paths:
            return self._project.sources

        expanded_file_paths = flatten([d.rglob("*.*") if d.is_dir() else [d] for d in file_paths])
        return [c.resolve() for c in expanded_file_paths if c.resolve() in self._project.sources]

    def compile(self) -> Dict[str, ContractType]:
        # TODO: only compile selected contracts
        return self._project.load_contracts(self._use_cache)


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
@ape_cli_context()
def cli(cli_ctx, filepaths, use_cache, display_size):
    """
    Compiles the manifest for this project and saves the results
    back to the manifest.

    Note that ape automatically recompiles any changed contracts each time
    a project is loaded. You do not have to manually trigger a recompile.
    """
    source = _ContractsSource(use_cache)
    missing_source = not source.root.exists() or not source.root.iterdir()
    if not filepaths and missing_source:
        cli_ctx.logger.warning("No 'contracts/' directory detected")
        return

    selected_file_paths = source.select_paths(filepaths)
    source_file_paths = list(source.root.iterdir())
    unable_to_select_all = len(source_file_paths) > len(selected_file_paths)

    if not selected_file_paths or unable_to_select_all:
        _warn_for_missing_extensions(cli_ctx, selected_file_paths, source_file_paths)

    contract_types = source.compile()

    if display_size:
        _display_byte_code_sizes(cli_ctx, contract_types)


def _warn_for_missing_extensions(cli_ctx, registered_sources: List[Path], all_sources: List[Path]):
    """
    Figures out what extensions are missing from registered compilers and warns
    the user about them.
    """
    extensions_unable_to_compile = set()
    for path in all_sources:
        if path not in registered_sources:
            extensions_unable_to_compile.add(path.suffix)

    if extensions_unable_to_compile:
        extensions_str = ", ".join(extensions_unable_to_compile)
        message = f"No compilers detected for the following extensions: {extensions_str}"
    else:
        message = "Nothing to compile"

    cli_ctx.logger.warning(message)


def _display_byte_code_sizes(cli_ctx, contract_types: Dict[str, ContractType]):
    # Display bytecode size for *all* contract types (not just ones we compiled)
    code_size = []
    for contract in contract_types.values():
        if not contract.deploymentBytecode:
            continue  # Skip if not bytecode to display

        bytecode = contract.deploymentBytecode.bytecode

        if bytecode:
            code_size.append((contract.contractName, len(bytecode) // 2))

    if not code_size:
        cli_ctx.logger.info("No contracts with bytecode to display")
        return

    click.echo()
    click.echo("============ Deployment Bytecode Sizes ============")
    indent = max(len(i[0]) for i in code_size)
    for name, size in sorted(code_size, key=lambda k: k[1], reverse=True):
        pct = size / 24577
        # pct_color = color(next((i[1] for i in CODESIZE_COLORS if pct >= i[0]), ""))
        # TODO Get colors fixed for bytecode size output
        # click.echo(f"  {name:<{indent}}  -  {size:>6,}B  ({pct_color}{pct:.2%}{color})")
        click.echo(f"  {name:<{indent}}  -  {size:>6,}B  ({pct:.2%})")

    click.echo()
