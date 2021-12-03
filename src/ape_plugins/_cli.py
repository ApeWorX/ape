import subprocess
import sys
from typing import List, Set

import click

from ape import config
from ape.cli import ape_cli_context, skip_confirmation_option
from ape.plugins import clean_plugin_name, plugin_manager
from ape.utils import get_package_version, github_client
from ape_plugins.utils import (
    CORE_PLUGINS,
    extract_module_and_package_install_names,
    is_plugin_installed,
)


@click.group(short_help="Manage ape plugins")
def cli():
    """
    Command-line helper for managing installed plugins.
    """


def _display_section(header: str, lines: List[Set[str]]):
    click.echo(header)
    for output in lines:
        if output:
            formatted_output = _format_output(output)
            click.echo("  {}".format("\n  ".join(formatted_output)))


def _format_output(plugins_list: Set[str]) -> Set:
    output = set()
    for i in plugins_list:
        text = i.replace("ape_", "")
        output.add(text)
    return output


@cli.command(name="list", short_help="Display plugins")
@click.option(
    "-a",
    "--all",
    "display_all",
    default=False,
    is_flag=True,
    help="Display all plugins installed and available (including Core)",
)
@ape_cli_context()
def _list(cli_ctx, display_all):
    installed_first_class_plugins = set()
    installed_second_class_plugins = set()
    installed_second_class_plugins_no_version = set()
    installed_third_class_plugins = set()

    for name, plugin in plugin_manager.list_name_plugin():
        version = get_package_version(name)

        if name in CORE_PLUGINS:
            if not display_all:
                continue  # NOTE: Skip 1st class plugins unless specified

            installed_first_class_plugins.add(name)

        elif name in github_client.available_plugins:
            installed_second_class_plugins.add(f"{name}     {version}")
            installed_second_class_plugins_no_version.add(name)

        elif name not in CORE_PLUGINS or name not in github_client.available_plugins:
            installed_third_class_plugins.add(f"{name}      {version})")
        else:
            cli_ctx.logger.error(f"{name} is not a plugin.")

    sections = {}

    # First Class Plugins
    if display_all:
        sections["Installed Core Plugins"] = [installed_first_class_plugins]

    # Second and Third Class Plugins
    available_second = list(
        github_client.available_plugins - installed_second_class_plugins_no_version
    )

    if installed_second_class_plugins:
        sections["Installed Plugins"] = [
            installed_second_class_plugins,
            installed_third_class_plugins,
        ]

    elif not display_all:
        # user has no plugins installed | cant verify installed plugins
        if available_second:
            click.echo("There are available plugins to install, use -a to list all plugins ")

    if display_all:

        available_second_output = _format_output(available_second)
        if available_second_output:

            sections["Available Plugins"] = [available_second_output]

        else:
            if github_client.available_plugins:
                click.echo("You have installed all the available Plugins\n")

    for i in range(0, len(sections)):
        header = list(sections.keys())[i]
        output = sections[header]
        _display_section(f"{header}:", output)

        if i < (len(sections) - 1):
            click.echo()


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

    if plugin in CORE_PLUGINS:
        cli_ctx.abort(f"Cannot add 1st class plugin '{plugin}'")

    elif is_plugin_installed(plugin):
        cli_ctx.abort(f"Plugin '{plugin}' already installed")

    elif (
        plugin in github_client.available_plugins
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
            module_name in github_client.available_plugins
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

    elif plugin in CORE_PLUGINS:
        cli_ctx.abort(f"Cannot remove 1st class plugin '{plugin}'")

    elif skip_confirmation or click.confirm(
        f"Remove plugin '{plugin} ({get_package_version(plugin)})'"
    ):
        # NOTE: Be *extremely careful* with this command, as it modifies the user's
        #       installed packages, to potentially catastrophic results
        # NOTE: This is not abstracted into another function *on purpose*
        subprocess.call([sys.executable, "-m", "pip", "uninstall", "--quiet", "-y", plugin])
