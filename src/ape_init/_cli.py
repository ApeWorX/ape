import shutil
from pathlib import Path

import click

from ape.cli import ape_cli_context
from ape.managers.config import CONFIG_FILE_NAME
from ape.utils import github_client

GITIGNORE_CONTENT = """
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


@click.command(short_help="Initialize an ape project")
@ape_cli_context()
@click.option("--github", metavar="github-org/repo", help="Clone a template from Github")
def cli(cli_ctx, github):
    """
    ``ape init`` allows the user to create an ape project with
    default folders and ape-config.yaml.
    """
    if github:
        github_client.clone_repo(github, Path.cwd())
        shutil.rmtree(Path.cwd() / ".git")
    else:
        project_folder = Path.cwd()

        for folder_name in ("contracts", "tests", "scripts"):
            # Create target Directory
            folder = project_folder / folder_name
            if folder.exists():
                cli_ctx.logger.warning(f"'{folder}' exists")
            else:
                folder.mkdir()

        git_ignore_path = project_folder / ".gitignore"
        if git_ignore_path.exists():
            cli_ctx.logger.warning(f"Unable to create .gitignore: '{git_ignore_path}' file exists.")
        else:
            git_ignore_path.touch()
            git_ignore_path.write_text(GITIGNORE_CONTENT.lstrip())

        ape_config = project_folder / CONFIG_FILE_NAME
        if ape_config.exists():
            cli_ctx.logger.warning(f"'{ape_config}' exists")
        else:
            project_name = click.prompt("Please enter project name")
            ape_config.write_text(f"name: {project_name}\n")
            cli_ctx.logger.success(f"{project_name} is written in {CONFIG_FILE_NAME}")
