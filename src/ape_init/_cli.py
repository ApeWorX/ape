import shutil
from pathlib import Path

import click

from ape.cli import Abort, ape_cli_context
from ape.utils import github_client


@click.command(short_help="Initalize an ape project")
@ape_cli_context()
@click.option("--github")
def cli(cli_ctx, github):
    if github:
        try:
            github_client.clone_repo(github, Path.cwd())
        except Exception as err:
            raise Abort(f"({type(err).__name__}) {err.data}") from err

        shutil.rmtree(Path.cwd() / ".git")

    else:
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
