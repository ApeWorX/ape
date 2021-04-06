import os
import subprocess
import sys
from pathlib import Path
from typing import Set

import click
from github import Github

from ape.plugins import clean_plugin_name, plugin_manager

# Plugins included with ape core
FIRST_CLASS_PLUGINS: Set[str] = {
    d.name for d in Path(__file__).parent.parent.iterdir() if d.is_dir and d.name.startswith("ape_")
}

# Plugins maintained OSS by ApeWorX (and trusted)
SECOND_CLASS_PLUGINS: Set[str] = set()

# TODO: Should the github client be in core?
if "GITHUB_ACCESS_TOKEN" in os.environ:
    author = Github(os.environ["GITHUB_ACCESS_TOKEN"]).get_organization("ApeWorX")

    SECOND_CLASS_PLUGINS = {
        repo.name for repo in author.get_repos() if repo.name.startswith("ape-")
    }


def is_plugin_installed(plugin: str) -> bool:
    try:
        __import__(plugin)
        return True
    except ImportError:
        return False


def get_plugin_version(plugin: str) -> str:
    if not is_plugin_installed(plugin):
        return ""

    pkg = __import__(plugin)
    if hasattr(pkg, "__version__"):
        return pkg.__version__

    else:
        return "<unknown>"


@click.group(short_help="Manage ape plugins")
def cli():
    """
    Command-line helper for managing installed plugins.
    """


@cli.command(name="list", short_help="List installed plugins")
def _list():
    click.echo("Installed plugins:")
    for name, plugin in plugin_manager.list_name_plugin():
        version_str = ""
        if hasattr(plugin, "__version__"):
            version_str = f" ({plugin.__version__})"
        elif name in FIRST_CLASS_PLUGINS:
            version_str = " (core)"

        click.echo(f"  {name}{version_str}")


@cli.command(short_help="Install an ape plugin")
@click.argument("plugin")
def add(plugin):
    if plugin.startswith("ape"):
        raise click.ClickException(f"Namespace 'ape' in '{plugin}' is not required")

    # NOTE: Add namespace prefix (prevents arbitrary installs)
    plugin = f"ape-{clean_plugin_name(plugin)}"

    if plugin in FIRST_CLASS_PLUGINS:
        raise click.ClickException(f"Cannot add 1st class plugin '{plugin}'")

    elif is_plugin_installed(plugin):
        raise click.ClickException(f"Plugin '{plugin}' already installed")

    elif plugin in SECOND_CLASS_PLUGINS or click.confirm(
        f"Install unknown 3rd party plugin '{plugin}'?"
    ):
        # NOTE: Be *extremely careful* with this command, as it modifies the user's
        #       installed packages, to potentially catastrophic results
        # NOTE: This is not abstracted into another function *on purpose*
        subprocess.call([sys.executable, "-m", "pip", "install", plugin])


@cli.command(short_help="Uninstall an ape plugin")
@click.argument("plugin")
def remove(plugin):
    if plugin.startswith("ape"):
        raise click.ClickException(f"Namespace 'ape' in '{plugin}' is not required")

    # NOTE: Add namespace prefix (match behavior of `install`)
    plugin = f"ape-{clean_plugin_name(plugin)}"

    if not is_plugin_installed(plugin):
        raise click.ClickException(f"Plugin '{plugin}' is not installed")

    elif plugin in FIRST_CLASS_PLUGINS:
        raise click.ClickException(f"Cannot remove 1st class plugin '{plugin}'")

    elif click.confirm(f"Remove plugin '{plugin} ({get_plugin_version(plugin)})'"):
        # NOTE: Be *extremely careful* with this command, as it modifies the user's
        #       installed packages, to potentially catastrophic results
        # NOTE: This is not abstracted into another function *on purpose*
        subprocess.call([sys.executable, "-m", "pip", "install", plugin])
