import pathlib
import shutil
from pathlib import Path
from typing import List

import click

from ape.cli import ape_cli_context
from ape.utils import github_client

try:
    import tomllib
# backwards compatibility
except ModuleNotFoundError:
    import tomli as tomllib


def read_dependencies_from_toml(file_path, cli_ctx) -> List[str]:

    with open("./pyproject.toml", "rb") as file:
        try:
            data = tomllib.load(file)
        except FileNotFoundError:
            cli_ctx.logger.warning(
                f"Unable to populate contnets from pyproject.toml file. {file_path} doesn't exists."
            )

        except tomli.TOMLDecodeError:
            cli_ctx.logger.warning(f"Error reading {file_path} file.")

    # Extract the 'tool.poetry.dependencies' section
    dependencies = data.get("tool", {}).get("poetry", {}).get("dependencies", {})

    # Check each dependency to see if it starts with 'ape-', because we know these are the ape plugins
    ape_plugins = [dep[4:] for dep in dependencies if dep.startswith("ape-")]

    return ape_plugins


def write_ape_config_yml(dependencies: List[str], file_to_write: pathlib.PosixPath):
    dependency_text = "plugins:\n" + "\n".join(
        [f"  - name: {dependency}" for dependency in dependencies]
    )
    file_to_write.write_text(dependency_text)


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
        if ape_config.is_file():
            cli_ctx.logger.warning(f"'{ape_config}' exists")
        else:
            project_name = click.prompt("Please enter project name")
            ape_config.write_text(f"name: {project_name}\n")
            cli_ctx.logger.success(f"{project_name} is written in ape-config.yaml")

        pyproject_toml = project_folder / "pyproject.toml"
        if pyproject_toml.is_file():
            dependencies = read_dependencies_from_toml(pyproject_toml, cli_ctx)
            write_ape_config_yml(dependencies, ape_config)
            cli_ctx.logger.success(
                f"Generated {ape_config} based on the currect pyproject.toml file"
            )
