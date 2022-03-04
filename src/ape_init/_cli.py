import shutil
from pathlib import Path

import click

from ape.cli import ape_cli_context
from ape.utils import github_client


@click.command(short_help="Initalize an ape project")
@ape_cli_context()
@click.option(
    "--github", metavar="GH_username/repo", help="Add github_username/repository to clone project"
)
def cli(cli_ctx, github):
    """
    Ape Init allows the user to create an ape project with
    default folders and ape-config.yaml

        project_name/\n
            contracts/\n
            tests/\n
            scripts/\n
            ape-config.yaml\n

    ape-config.yaml is to manage project dependencies such as plugins.
    Adding plugins is format sensitive.

    Ape init has an [OPTIONAL] argument to clone repositories
    `ape init --github github_username/repository_name`
    """
    if github:
        github_client.clone_repo(github, Path.cwd())
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
