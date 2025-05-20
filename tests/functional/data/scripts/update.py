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
@click.argument("contract_path", callback=_contract_callback)
def cli(cli_ctx, contract_path):
    cm = cli_ctx.compiler_manager
    compiler = "vyper" if contract_path.suffix == ".vy" else "solidity"
    code = contract_path.read_text(encoding="utf-8")
    destination = ARTIFACTS_PATH / f"{contract_path.stem}.json"
    contract_type = cm.compile_source(compiler, code, contractName=contract_path.stem).contract_type

    if contract_type.source_id is None:
        contract_type.source_id = f"{contract_path.stem}.json"

    json_text = contract_type.model_dump_json()
    destination.unlink()
    destination.write_text(json_text, encoding="utf-8")
    click.echo("Done!")
