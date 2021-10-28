import subprocess
import sys

import click
from ape_plugins.utils import (
    FIRST_CLASS_PLUGINS,
    SECOND_CLASS_PLUGINS,
    extract_module_and_package_install_names,
    is_plugin_installed,
)

from ape import config
from ape.cli import ape_cli_context, skip_confirmation_option
from ape.plugins import clean_plugin_name, plugin_manager
from ape.utils import get_package_version


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
@ape_cli_context()
def _list(cli_ctx, display_all):
    installed_second = set()
    installed_first = set()
    installed_third = set()
    for name, plugin in plugin_manager.list_name_plugin():
        version_str = ""
        version = get_package_version(name)

        if name in FIRST_CLASS_PLUGINS:
            if not display_all:

                continue  # NOTE: Skip 1st class plugins unless specified
            #version_str = " (core)"
            version_str = f" ({version})"
            installed_first.add(f"{name}")

        elif name in SECOND_CLASS_PLUGINS:
            if not display_all:
                continue
            #version_str = "( second)"
            version_str = f" ({version})"
            installed_second.add(f"{name}")

        elif name not in FIRST_CLASS_PLUGINS or name not in SECOND_CLASS_PLUGINS:
            #version_str = "( third)"
            version_str = f" ({version})"
            installed_third.add(f"{name}    ({version})")
        else:
            print(name + "is not 1st, 2nd, or 3rd party plugin")

    uninstalled_first = (FIRST_CLASS_PLUGINS - installed_first)
    uninstalled_second = (SECOND_CLASS_PLUGINS - installed_second)

    if installed_first:
        click.echo("(CORE) Installed First Class Plugins:")
        click.echo("  " + "\n  ".join(installed_first))
    else:
        cli_ctx.logger.info("No First Class plugins installed")

    if installed_second:
        click.echo("\n"+ "(2nd) Installed Second Class Plugins:")
        click.echo("  " + "\n  ".join(installed_second))
    else:
        cli_ctx.logger.info("No Second Class Plugins installed")


    if uninstalled_first:
        click.echo("\n"+ "You are missing these CORE First Class Plugins:")
        click.echo("  " + "\n  ".join(uninstalled_first))
    
    if uninstalled_second:
        click.echo("\n"+ "(2nd) UNINSTALLED Second Class Plugins:")
        click.echo("  " + "\n  ".join(uninstalled_second))
    else:
        cli_ctx.logger.info("You have installed all the Second Class Plugins")


@cli.command(short_help="Install an ape plugin")
@click.argument("plugin")
@click.option("-v", "--version", help="Specify version (Default is latest)")
@skip_confirmation_option(help="Don't ask for confirmation to add the plugin")
@ape_cli_context()
def add(cli_ctx, plugin, version, skip_confirmation):
    if plugin.startswith("ape"):
        cli_ctx.abort(f"Namespace 'ape' in '{plugin}' is not required")

    # NOTE: Add namespace prefix (prevents arbitrary installs)
    plugin = f"ape_{clean_plugin_name(plugin)}"

    if version:
        plugin = f"{plugin}=={version}"

    if plugin in FIRST_CLASS_PLUGINS:
        cli_ctx.abort(f"Cannot add 1st class plugin '{plugin}'")

    elif is_plugin_installed(plugin):
        cli_ctx.abort(f"Plugin '{plugin}' already installed")

    elif (
        plugin in SECOND_CLASS_PLUGINS
        or skip_confirmation
        or click.confirm(f"Install unknown 3rd party plugin '{plugin}'?")
    ):
        cli_ctx.logger.info(f"Installing {plugin}...")
        # NOTE: Be *extremely careful* with this command, as it modifies the user's
        #       installed packages, to potentially catastrophic results
        # NOTE: This is not abstracted into another function *on purpose*
        subprocess.call([sys.executable, "-m", "pip", "install", "--quiet", plugin])


@cli.command(short_help="Install all plugins in the local config file")
@ape_cli_context()
@skip_confirmation_option("Don't ask for confirmation to install the plugins")
def install(cli_ctx, skip_confirmation):
    plugins = config.get_config("plugins") or []
    for plugin in plugins:
        module_name, package_name = extract_module_and_package_install_names(plugin)
        if not is_plugin_installed(module_name) and (
            module_name in SECOND_CLASS_PLUGINS
            or skip_confirmation
            or click.confirm(f"Install unknown 3rd party plugin '{package_name}'?")
        ):
            cli_ctx.logger.info(f"Installing {package_name}...")
            # NOTE: Be *extremely careful* with this command, as it modifies the user's
            #       installed packages, to potentially catastrophic results
            # NOTE: This is not abstracted into another function *on purpose*
            subprocess.call([sys.executable, "-m", "pip", "install", "--quiet", f"{package_name}"])


@cli.command(short_help="Uninstall an ape plugin")
@click.argument("plugin")
@skip_confirmation_option("Don't ask for confirmation to remove the plugin")
@ape_cli_context()
def remove(cli_ctx, plugin, skip_confirmation):
    if plugin.startswith("ape"):
        cli_ctx.abort(f"Namespace 'ape' in '{plugin}' is not required")

    # NOTE: Add namespace prefix (match behavior of ``install``)
    plugin = f"ape_{clean_plugin_name(plugin)}"

    if not is_plugin_installed(plugin):
        cli_ctx.abort(f"Plugin '{plugin}' is not installed")

    elif plugin in FIRST_CLASS_PLUGINS:
        cli_ctx.abort(f"Cannot remove 1st class plugin '{plugin}'")

    elif skip_confirmation or click.confirm(
        f"Remove plugin '{plugin} ({get_package_version(plugin)})'"
    ):
        # NOTE: Be *extremely careful* with this command, as it modifies the user's
        #       installed packages, to potentially catastrophic results
        # NOTE: This is not abstracted into another function *on purpose*
        subprocess.call([sys.executable, "-m", "pip", "uninstall", "--quiet", "-y", plugin])