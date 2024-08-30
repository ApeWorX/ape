from pathlib import Path

import click

from ape.cli import ape_cli_context

BASE_PATH = Path(__file__).parent.parent
SOURCES_PATH = BASE_PATH / "sources"
ARTIFACTS_PATH = BASE_PATH / "contracts" / "ethereum" / "local"


def _contract_callback(ctx, param, val):
    for ext in ("sol", "vy"):
        path = SOURCES_PATH / f"{val}.{ext}"
        if path.is_file():
            return path

    raise click.BadArgumentUsage(f"Contract not found: {val}")


@click.command()
@ape_cli_context()
@click.argument("contract", callback=_contract_callback)
def cli(cli_ctx, contract):
    cm = cli_ctx.compiler_manager
    compiler = "vyper" if contract.suffix == ".vy" else "solidity"
    code = contract.read_text(encoding="utf-8")
    destination = ARTIFACTS_PATH / f"{contract.stem}.json"
    contract_type = cm.compile_source(compiler, code, contractName=contract.stem)
    destination.unlink()
    destination.write_text(contract_type.model_dump_json())
    click.echo("Done!")
