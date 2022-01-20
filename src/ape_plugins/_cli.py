import subprocess
import sys
from os import getcwd
from pathlib import Path
from typing import List, Set

import click

from ape import config
from ape.cli import ape_cli_context, skip_confirmation_option
from ape.managers.config import CONFIG_FILE_NAME
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

    plugin_list = plugin_manager.list_name_plugin()
    plugin_names = [p[0] for p in plugin_list]
    longest_plugin_name = len(max(plugin_names, key=len))
    space_buffer = 4

    for name, _ in plugin_list:
        version = get_package_version(name)
        spacing = (longest_plugin_name - len(name) + space_buffer) * " "
        if name in CORE_PLUGINS:
            if not display_all:
                continue  # NOTE: Skip 1st class plugins unless specified

            installed_first_class_plugins.add(name)

        elif name in github_client.available_plugins:
            installed_second_class_plugins.add(f"{name}{spacing}{version}")
            installed_second_class_plugins_no_version.add(name)

        elif name not in CORE_PLUGINS or name not in github_client.available_plugins:
            installed_third_class_plugins.add(f"{name}{spacing}{version})")
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


def upgrade_option(help: str = ""):
    """
    A ``click.option`` for upgrading plugins (``--upgrade``).

    Args:
        help (str): CLI option help text. Defaults to ``""``.
    """

    return click.option(
        "-U",
        "--upgrade",
        default=False,
        is_flag=True,
        help=help,
    )


@cli.command(short_help="Install an ape plugin")
@click.argument("plugin")
@click.option("--version", help="Specify version (Default is latest)")
@skip_confirmation_option(help="Don't ask for confirmation to add the plugin")
@ape_cli_context()
@upgrade_option(help="Upgrade the plugin to the newest available version")
def add(cli_ctx, plugin, version, skip_confirmation, upgrade):
    args = [sys.executable, "-m", "pip", "install", "--quiet"]
    if plugin.startswith("ape"):
        cli_ctx.abort(f"Namespace 'ape' in '{plugin}' is not required")

    # NOTE: Add namespace prefix (prevents arbitrary installs)
    plugin = f"ape_{clean_plugin_name(plugin)}"
    if version:
        plugin = f"{plugin}=={version}"

    if plugin in CORE_PLUGINS:
        cli_ctx.abort(f"Cannot add 1st class plugin '{plugin}'")

    elif is_plugin_installed(plugin):
        if upgrade:
            cli_ctx.logger.info(f"Updating '{plugin}'...")
            args.append("--upgrade")
            args.append(plugin)
            result = subprocess.call(args)

            if result == 0 and is_plugin_installed(plugin):
                cli_ctx.logger.success(f"Plugin '{plugin}' has been upgraded.")
            else:
                cli_ctx.logger.error(f"Failed to add '{plugin}'.")
                sys.exit(1)
        else:
            cli_ctx.logger.warning(
                f"{plugin} is already installed. "
                f"Use the '--upgrade' if you want to update '{plugin}'."
            )

    elif (
        plugin in github_client.available_plugins
        or skip_confirmation
        or click.confirm(f"Install unknown 3rd party plugin '{plugin}'?")
    ):
        cli_ctx.logger.info(f"Installing '{plugin}'...")
        # NOTE: Be *extremely careful* with this command, as it modifies the user's
        #       installed packages, to potentially catastrophic results
        # NOTE: This is not abstracted into another function *on purpose*

        args.append(plugin)
        result = subprocess.call(args)
        if result == 0 and is_plugin_installed(plugin):
            cli_ctx.logger.success(f"Plugin '{plugin}' has been added.")
        else:
            cli_ctx.logger.error(f"Failed to add '{plugin}'.")
            sys.exit(1)


@cli.command(short_help="Install all plugins in the local config file")
@ape_cli_context()
@skip_confirmation_option("Don't ask for confirmation to install the plugins")
@upgrade_option(help="Upgrade the plugin to the newest available version")
def install(cli_ctx, skip_confirmation, upgrade):
    any_install_failed = False
    cwd = getcwd()
    config_path = Path(cwd) / CONFIG_FILE_NAME
    cli_ctx.logger.info(f"Installing plugins from config file at {config_path}")
    plugins = config.get_config("plugins") or []
    for plugin in plugins:
        args = [sys.executable, "-m", "pip", "install", "--quiet"]
        module_name, package_name = extract_module_and_package_install_names(plugin)

        available_plugin = module_name in github_client.available_plugins
        installed_plugin = is_plugin_installed(module_name)
        # if plugin is installed but not a 2nd class. It must be a third party
        if not installed_plugin and not available_plugin:
            cli_ctx.logger.warning(f"Plugin '{module_name}' is not an trusted plugin.")
            any_install_failed = True
        # check for installed check the config.yaml
        elif installed_plugin and available_plugin:
            if upgrade:
                cli_ctx.logger.info(f"Updating '{module_name}'...")
                args.append("--upgrade")
                args.append(module_name)
                result = subprocess.call(args)
                if result == 0 and is_plugin_installed(module_name):
                    cli_ctx.logger.success(f"Plugin '{module_name}' has been upgraded.")
                else:
                    cli_ctx.logger.error(f"Failed to upgrade '{module_name}'.")
                    any_install_failed = True
            else:
                cli_ctx.logger.warning(
                    f"{module_name} is already installed. "
                    f"Use the '--upgrade' option if you want to update '{plugin}'"
                )

        if not is_plugin_installed(module_name) and (
            module_name in github_client.available_plugins
            or skip_confirmation
            or click.confirm(f"Install unknown 3rd party plugin '{package_name}'?")
        ):
            cli_ctx.logger.info(f"Installing {package_name}...")
            # NOTE: Be *extremely careful* with this command, as it modifies the user's
            #       installed packages, to potentially catastrophic results
            # NOTE: This is not abstracted into another function *on purpose*
            if upgrade:
                args.append("--upgrade")
            args.append(package_name)
            result = subprocess.call(args)
            plugin_got_installed = is_plugin_installed(module_name)
            if result == 0 and plugin_got_installed:
                cli_ctx.logger.success(f"Plugin '{module_name}' has been added.")
            else:
                cli_ctx.logger.error(f"Failed to add '{package_name}'.")
                any_install_failed = True
    if any_install_failed:
        sys.exit(1)


@cli.command(short_help="Uninstall all plugins in the local config file")
@ape_cli_context()
@skip_confirmation_option("Don't ask for confirmation to install the plugins")
def uninstall(cli_ctx, skip_confirmation):
    any_uninstall_failed = False
    cwd = getcwd()
    config_path = Path(cwd) / CONFIG_FILE_NAME
    cli_ctx.logger.info(f"Uninstalling plugins from config file at {config_path}")

    plugins = config.get_config("plugins") or []
    for plugin in plugins:
        module_name, package_name = extract_module_and_package_install_names(plugin)

        available_plugin = module_name in github_client.available_plugins
        plugin_still_installed = is_plugin_installed(module_name)

        # if plugin is installed but not a 2nd class. It must be a third party
        if plugin_still_installed and not available_plugin:
            cli_ctx.logger.warning(
                f"Plugin '{module_name}' is not installed but not in available plugins."
                f" Please uninstall outside of Ape."
            )
            any_uninstall_failed = True
            pass
        # check for installed check the config.yaml
        elif not plugin_still_installed:
            cli_ctx.logger.warning(f"Plugin '{module_name}' is not installed.")
            any_uninstall_failed = True
            pass

        # if plugin is installed and 2nd class. We should uninstall it
        if plugin_still_installed and (available_plugin or skip_confirmation):
            cli_ctx.logger.info(f"Uninstalling {package_name}...")
            # NOTE: Be *extremely careful* with this command, as it modifies the user's
            #       installed packages, to potentially catastrophic results
            # NOTE: This is not abstracted into another function *on purpose*

            args = [sys.executable, "-m", "pip", "uninstall", "--quiet"]
            if skip_confirmation:
                args.append("-y")
            args.append(package_name)

            result = subprocess.call(args)
            plugin_still_installed = is_plugin_installed(module_name)

            if result == 0 and not plugin_still_installed:
                cli_ctx.logger.success(f"Plugin '{package_name}' has been removed.")

            else:
                cli_ctx.logger.error(f"Failed to remove '{package_name}'.")
                any_uninstall_failed = True
    if any_uninstall_failed:
        sys.exit(1)


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
        result = subprocess.call(
            [sys.executable, "-m", "pip", "uninstall", "--quiet", "-y", plugin]
        )
        plugin_still_installed = is_plugin_installed(plugin)
        if result == 0 and not plugin_still_installed:
            cli_ctx.logger.success(f"Plugin '{plugin}' has been removed.")
        else:
            cli_ctx.logger.error(f"Failed to remove '{plugin}'.")
            sys.exit(1)
