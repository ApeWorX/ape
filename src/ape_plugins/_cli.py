import os
import subprocess
import sys
from pathlib import Path
from typing import Set

import click
from github import Github

from ape import config
from ape.plugins import clean_plugin_name, plugin_manager
from ape.utils import Abort, get_package_version, notify

# Plugins included with ape core
FIRST_CLASS_PLUGINS: Set[str] = {
    d.name for d in Path(__file__).parent.parent.iterdir() if d.is_dir and d.name.startswith("ape_")
}

# Plugins maintained OSS by ApeWorX (and trusted)
SECOND_CLASS_PLUGINS: Set[str] = set()

# TODO: Should the github client be in core?
# TODO: Handle failures with connecting to github (potentially cached on disk?)
if "GITHUB_ACCESS_TOKEN" in os.environ:
    author = Github(os.environ["GITHUB_ACCESS_TOKEN"]).get_organization("ApeWorX")

    SECOND_CLASS_PLUGINS = {
        repo.name.replace("-", "_") for repo in author.get_repos() if repo.name.startswith("ape-")
    }

else:
    notify("WARNING", "$GITHUB_ACCESS_TOKEN not set, skipping 2nd class plugins")


def is_plugin_installed(plugin: str) -> bool:
    try:
        __import__(plugin)
        return True
    except ImportError:
        return False


@click.group(short_help="Manage ape plugins")
def cli():
    """
    Command-line helper for managing installed plugins.
    """


@cli.command(name="list", short_help="List installed plugins")
@click.option(
    "-a",
    "--all",
    "display_all",
    default=False,
    is_flag=True,
    help="Display all plugins (including Core)",
)
def _list(display_all):
    plugins = []
    for name, plugin in plugin_manager.list_name_plugin():
        version_str = ""
        version = get_package_version(name)

        if name in FIRST_CLASS_PLUGINS:
            if not display_all:
                continue  # NOTE: Skip 1st class plugins unless specified
            version_str = " (core)"

        elif version:
            version_str = f" ({version})"

        plugins.append(f"{name}{version_str}")

    if plugins:
        click.echo("Installed plugins:")
        click.echo("  " + "\n  ".join(plugins))

    else:
        notify("INFO", "No plugins installed")


@cli.command(short_help="Install an ape plugin")
@click.argument("plugin")
@click.option("-v", "--version", help="Specify version (Default is latest)")
def add(plugin, version):
    if plugin.startswith("ape"):
        raise Abort(f"Namespace 'ape' in '{plugin}' is not required")

    # NOTE: Add namespace prefix (prevents arbitrary installs)
    plugin = f"ape_{clean_plugin_name(plugin)}"

    if version:
        plugin = f"{plugin}=={version}"

    if plugin in FIRST_CLASS_PLUGINS:
        raise Abort(f"Cannot add 1st class plugin '{plugin}'")

    elif is_plugin_installed(plugin):
        raise Abort(f"Plugin '{plugin}' already installed")

    elif plugin in SECOND_CLASS_PLUGINS or click.confirm(
        f"Install unknown 3rd party plugin '{plugin}'?"
    ):
        notify("INFO", f"Installing {plugin}...")
        # NOTE: Be *extremely careful* with this command, as it modifies the user's
        #       installed packages, to potentially catastrophic results
        # NOTE: This is not abstracted into another function *on purpose*
        subprocess.call([sys.executable, "-m", "pip", "install", "--quiet", plugin])


@cli.command(short_help="Install all plugins in the local config file")
@click.pass_context
def install(ctx):
    for plugin, version in config.get_config("plugins").items():
        if not plugin.startswith("ape-"):
            raise Abort(f"Namespace 'ape' required in config item '{plugin}'")

        if not is_plugin_installed(plugin.replace("-", "_")) and (
            plugin.replace("-", "_") in SECOND_CLASS_PLUGINS
            or click.confirm(f"Install unknown 3rd party plugin '{plugin}'?")
        ):
            notify("INFO", f"Installing {plugin}...")
            # NOTE: Be *extremely careful* with this command, as it modifies the user's
            #       installed packages, to potentially catastrophic results
            # NOTE: This is not abstracted into another function *on purpose*
            subprocess.call(
                [sys.executable, "-m", "pip", "install", "--quiet", f"{plugin}=={version}"]
            )


@cli.command(short_help="Uninstall an ape plugin")
@click.argument("plugin")
@click.option(
    "-y",
    "--yes",
    "skip_confirmation",
    default=False,
    is_flag=True,
    help="Don't ask for confirmation to remove plugin",
)
def remove(plugin, skip_confirmation):
    if plugin.startswith("ape"):
        raise Abort(f"Namespace 'ape' in '{plugin}' is not required")

    # NOTE: Add namespace prefix (match behavior of `install`)
    plugin = f"ape_{clean_plugin_name(plugin)}"

    if not is_plugin_installed(plugin):
        raise Abort(f"Plugin '{plugin}' is not installed")

    elif plugin in FIRST_CLASS_PLUGINS:
        raise Abort(f"Cannot remove 1st class plugin '{plugin}'")

    elif skip_confirmation or click.confirm(
        f"Remove plugin '{plugin} ({get_package_version(plugin)})'"
    ):
        # NOTE: Be *extremely careful* with this command, as it modifies the user's
        #       installed packages, to potentially catastrophic results
        # NOTE: This is not abstracted into another function *on purpose*
        subprocess.call([sys.executable, "-m", "pip", "uninstall", "--quiet", "-y", plugin])
