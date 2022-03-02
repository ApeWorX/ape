from pathlib import Path

import click

from ape.cli import ape_cli_context


@click.command(short_help="Initalize an ape project")
@ape_cli_context()
def cli(cli_ctx):
    project_folder = Path.cwd()

    for folder_name in ["contracts", "tests", "scripts"]:
        # Create target Directory
        folder = project_folder / folder_name
        if folder.exists():
            cli_ctx.logger.warning(f"'{folder}' exists")
        else:
            folder.mkdir(exist_ok=False)

    ape_config = project_folder / "ape-config.yaml"
    if ape_config.exists():
        cli_ctx.logger.warning(f"'{ape_config}' exists")
    else:
        project_name = click.prompt("Please enter project name")
        ape_config.write_text(f"name: {project_name}\n")
