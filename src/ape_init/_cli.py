import shutil
from pathlib import Path

import click
from click import BadParameter

from ape.cli.options import ape_cli_context
from ape.utils._github import github_client

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


def validate_github_repo(ctx, param, value):
    if not value:
        return None

    elif value.count("/") != 1:
        raise BadParameter("Invalid GitHub parameter, must be in format 'org/repo'.", ctx, param)

    org, repo = value.split("/")
    if not org:
        raise BadParameter("Invalid GitHub parameter, missing 'org' value.")
    if not repo:
        raise BadParameter("Invalid GitHub parameter, missing 'repo' value.")

    return (org, repo)


@click.command(short_help="Initialize an ape project")
@ape_cli_context()
@click.option(
    "--github",
    metavar="github-org/repo",
    help="Clone a template from Github",
    callback=validate_github_repo,
)
def cli(cli_ctx, github):
    """
    ``ape init`` allows the user to create an ape project with
    default folders and ape-config.yaml.
    """
    if github:
        org, repo = github
        github_client.clone_repo(org, repo, Path.cwd())
        shutil.rmtree(Path.cwd() / ".git", ignore_errors=True)
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
            git_ignore_path.write_text(GITIGNORE_CONTENT.lstrip(), encoding="utf8")

        ape_config = project_folder / "ape-config.yaml"
        if ape_config.exists():
            cli_ctx.logger.warning(f"'{ape_config}' exists")
        else:
            project_name = click.prompt("Please enter project name")
            ape_config.write_text(f"name: {project_name}\n", encoding="utf8")
            cli_ctx.logger.success(f"{project_name} is written in ape-config.yaml")
