import click

from ape.compilers import load
from ape.package import PackageManifest
from ape.utils import notify


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
    Compiles the manifest for this project and saves the results
    back to the manifest.

    Note that ape automatically recompiles any changed contracts each time
    a project is loaded. You do not have to manually trigger a recompile.
    """

    # TODO
    # * Look for local manifest
    # * If not, look for local config
    # * If no config assume everything is default
    # * `contracts` allows selecting specific contracts to compile from manifest
    # Config should override defaults. If no config value, use default.
    # default config is the source of truth, the manifest is an artifact of the
    # config, both pre-and post procesing

    if not contracts:
        notify("ERROR", "No manifest argument provided")
        return

    manifest = PackageManifest.from_file(contracts[0])

    if not manifest.sources:
        notify("ERROR", "Manifest contains no sources to compile")
        return

    contract_types = {s.type for (n, s) in manifest.sources.items() if not s.type == ""}

    compilers = []

    for t in contract_types:
        try:
            compilers.append(load(t))
            click.echo(f"{compilers[-1].name} loaded to handle '{t}' contracts")
        except IndexError:
            click.echo(f"No compiler found for '{t}'")
            click.echo()
            continue

    for c in compilers:
        c.compile(manifest)

        if display_size:
            click.echo()
            click.echo("============ Deployment Bytecode Sizes ============")
            codesize = []
            for contract in manifest.contractTypes:
                bytecode = contract.deploymentBytecode.bytecode
                if bytecode:
                    codesize.append((contract.contractName, len(bytecode) // 2))
            indent = max(len(i[0]) for i in codesize)
            for name, size in sorted(codesize, key=lambda k: k[1], reverse=True):
                pct = size / 24577
                # pct_color = color(next((i[1] for i in CODESIZE_COLORS if pct >= i[0]), ""))
                # TODO Get colors fixed for bytecode size output
                # click.echo(f"  {name:<{indent}}  -  {size:>6,}B  ({pct_color}{pct:.2%}{color})")
                click.echo(f"  {name:<{indent}}  -  {size:>6,}B  ({pct:.2%})")
            click.echo()

    manifest.to_file(contracts[0])
