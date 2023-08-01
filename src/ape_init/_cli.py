import shutil
from pathlib import Path

import click

from ape.cli import ape_cli_context
from ape.utils import github_client


@click.command(short_help="Initalize an ape project")
@ape_cli_context()
@click.option("--github", metavar="github-org/repo", help="Clone a template from Github")
def cli(cli_ctx, github):
    """
    ``ape init`` allows the user to create an ape project with
    default folders and ape-config.yaml

    From more information:
    https://docs.apeworx.io/ape/stable/userguides/config.html
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

        git_ignore_path = project_folder / ".gitignore"
        if git_ignore_path.is_file():
            cli_ctx.logger.warning(f"Unable to create .gitignore: '{git_ignore_path}' file exists.")
        else:
            body = """
# Ape stuff
.build/
.cache/

# Python
.env
.venv
.pytest_cache
.python-version
__pycache__
"""
            git_ignore_path.touch()
            git_ignore_path.write_text(body.lstrip())

        ape_config = project_folder / "ape-config.yaml"
        if ape_config.exists():
            cli_ctx.logger.warning(f"'{ape_config}' exists")
        else:
            project_name = click.prompt("Please enter project name")
            ape_config.write_text(f"name: {project_name}\n")
            cli_ctx.logger.success(f"{project_name} is written in ape-config.yaml")
