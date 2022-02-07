import subprocess
import sys
from pathlib import Path
from typing import Collection, List, Set

import click

from ape import config
from ape.cli import ape_cli_context, incompatible_with, skip_confirmation_option
from ape.managers.config import CONFIG_FILE_NAME
from ape.plugins import plugin_manager
from ape.utils import github_client
from ape_plugins.utils import CORE_PLUGINS, ApePlugin, ModifyPluginsResultHandler


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


def _format_output(plugins_list: Collection[str]) -> Set:
    output = set()
    for i in plugins_list:
        text = i.replace("ape_", "")
        output.add(text)
    return output


def plugin_argument():
    return click.argument("plugin", callback=lambda ctx, param, value: ApePlugin(value))


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
        plugin = ApePlugin(name)
        spacing = (longest_plugin_name - len(plugin.name) + space_buffer) * " "
        if plugin.is_part_of_core:
            if not display_all:
                continue  # NOTE: Skip 1st class plugins unless specified

            installed_first_class_plugins.add(name)

        elif plugin.is_available:
            installed_second_class_plugins.add(f"{name}{spacing}{plugin.current_version}")
            installed_second_class_plugins_no_version.add(name)

        elif not plugin.is_part_of_core or not plugin.is_available:
            installed_third_class_plugins.add(f"{name}{spacing}{plugin.current_version}")
        else:
            cli_ctx.logger.error(f"'{plugin.name}' is not a plugin.")

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
            click.echo("No secondary plugins installed. Use '--all' to see available plugins.")

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


def upgrade_option(help: str = "", **kwargs):
    """
    A ``click.option`` for upgrading plugins (``--upgrade``).

    Args:
        help (str): CLI option help text. Defaults to ``""``.
    """

    return click.option("-U", "--upgrade", default=False, is_flag=True, help=help, **kwargs)


@cli.command(short_help="Install an ape plugin")
@plugin_argument()
@click.option("--version", help="Specify version (Default is latest)")
@skip_confirmation_option(help="Don't ask for confirmation to add the plugin")
@ape_cli_context()
@upgrade_option(
    help="Upgrade the plugin to the newest available version",
    cls=incompatible_with(["version"]),
)
def add(cli_ctx, plugin, version, skip_confirmation, upgrade):
    plugin.version_to_install = version
    result_handler = ModifyPluginsResultHandler(cli_ctx.logger, plugin)
    args = [sys.executable, "-m", "pip", "install", "--quiet"]

    if plugin.version_to_install and plugin.version_to_install == plugin.current_version:
        cli_ctx.logger.warning(f"Plugin '{plugin}' already installed.")
        return

    elif plugin.is_part_of_core:
        cli_ctx.abort(f"Cannot install core 'ape' plugin '{plugin.name}'.")

    elif plugin.is_installed and upgrade:
        cli_ctx.logger.info(f"Upgrading '{plugin.name}'...")
        args.extend(("--upgrade", plugin.package_name))

        version_before = plugin.current_version
        result = subprocess.call(args)
        if not result_handler.handle_upgrade_result(result, version_before):
            sys.exit(1)

    elif plugin.can_install and (
        plugin.is_available
        or skip_confirmation
        or click.confirm(f"Install unknown 3rd party plugin '{plugin.name}'?")
    ):
        cli_ctx.logger.info(f"Installing '{plugin}'...")
        # NOTE: Be *extremely careful* with this command, as it modifies the user's
        #       installed packages, to potentially catastrophic results
        # NOTE: This is not abstracted into another function *on purpose*

        args.append(plugin.install_str)
        result = subprocess.call(args)
        if not result_handler.handle_install_result(result):
            sys.exit(1)

    else:
        cli_ctx.logger.warning(
            f"Plugin '{plugin.name}' is already installed. Did you mean to include '--upgrade'?"
        )


@cli.command(short_help="Install all plugins in the local config file")
@ape_cli_context()
@skip_confirmation_option("Don't ask for confirmation to install the plugins")
@upgrade_option(help="Upgrade the plugin to the newest available version")
def install(cli_ctx, skip_confirmation, upgrade):
    config_path = Path.cwd() / CONFIG_FILE_NAME
    if not config_path.exists():
        cli_ctx.abort(f"'{config_path.name}' not found.")

    any_failures = False
    cli_ctx.logger.info(f"Installing plugins from config file at '{config_path}'.")
    plugins = config.get_config("plugins") or []
    for plugin_dict in plugins:
        plugin = ApePlugin.from_dict(plugin_dict)

        if plugin.is_part_of_core:
            cli_ctx.abort(f"Cannot install core 'ape' plugin '{plugin.name}'.")

        # if plugin is installed but not a 2nd class. It must be a third party
        if not plugin.is_installed and not plugin.is_available:
            cli_ctx.logger.warning(f"Plugin '{plugin.name}' is not an trusted plugin.")

        result_handler = ModifyPluginsResultHandler(cli_ctx.logger, plugin)
        args = [sys.executable, "-m", "pip", "install", "--quiet"]

        if upgrade:
            cli_ctx.logger.info(f"Upgrading '{plugin.name}'...")
            args.extend(("--upgrade", plugin.package_name))

            version_before = plugin.current_version
            result = subprocess.call(args)
            any_failures = result_handler.handle_upgrade_result(result, version_before)

        elif plugin.can_install and (
            plugin.is_available
            or skip_confirmation
            or click.confirm(f"Install unknown 3rd party plugin '{plugin.name}'?")
        ):
            cli_ctx.logger.info(f"Installing {plugin}...")
            args.append(plugin.install_str)

            # NOTE: Be *extremely careful* with this command, as it modifies the user's
            #       installed packages, to potentially catastrophic results
            # NOTE: This is not abstracted into another function *on purpose*
            result = subprocess.call(args)
            any_failures = not result_handler.handle_install_result(result)

        else:
            cli_ctx.logger.warning(
                f"'{plugin.name}' is already installed. " f"Did you mean to include '--upgrade'."
            )

    if any_failures:
        sys.exit(1)


@cli.command(short_help="Uninstall all plugins in the local config file")
@ape_cli_context()
@skip_confirmation_option("Don't ask for confirmation to install the plugins")
def uninstall(cli_ctx, skip_confirmation):
    config_path = Path.cwd() / CONFIG_FILE_NAME
    if not config_path.exists():
        cli_ctx.abort(f"'{config_path.name}' not found.")

    cli_ctx.logger.info(f"Uninstalling plugins from config file at '{config_path}'.")

    failures_occurred = False
    plugins = config.get_config("plugins") or []
    for plugin_dict in plugins:
        plugin = ApePlugin.from_dict(plugin_dict)
        result_handler = ModifyPluginsResultHandler(cli_ctx.logger, plugin)

        # if plugin is installed but not a 2nd class. It must be a third party
        if plugin.is_installed and not plugin.is_available:
            cli_ctx.logger.warning(
                f"Plugin '{plugin.name}' is not installed but not in available plugins."
                f" Please uninstall outside of Ape."
            )
            failures_occurred = True
            pass
        # check for installed check the config.yaml
        elif not plugin.is_installed:
            cli_ctx.logger.warning(f"Plugin '{plugin.name}' is not installed.")
            failures_occurred = True
            pass

        # if plugin is installed and 2nd class. We should uninstall it
        if plugin.is_installed and (
            skip_confirmation or click.confirm(f"Remove plugin '{plugin}'?")
        ):
            cli_ctx.logger.info(f"Uninstalling '{plugin.name}'...")
            args = [sys.executable, "-m", "pip", "uninstall", "--quiet", "-y", plugin.package_name]

            # NOTE: Be *extremely careful* with this command, as it modifies the user's
            #       installed packages, to potentially catastrophic results
            # NOTE: This is not abstracted into another function *on purpose*
            result = subprocess.call(args)
            failures_occurred = not result_handler.handle_uninstall_result(result)

    if failures_occurred:
        sys.exit(1)


@cli.command(short_help="Uninstall an ape plugin")
@plugin_argument()
@skip_confirmation_option("Don't ask for confirmation to remove the plugin")
@ape_cli_context()
def remove(cli_ctx, plugin, skip_confirmation):
    if not plugin.is_installed:
        cli_ctx.abort(f"Plugin '{plugin.name}' is not installed.")

    elif plugin in CORE_PLUGINS:
        cli_ctx.abort(f"Cannot remove 1st class plugin '{plugin.name}'.")

    elif skip_confirmation or click.confirm(f"Remove plugin '{plugin}'?"):
        result_handler = ModifyPluginsResultHandler(cli_ctx.logger, plugin)
        # NOTE: Be *extremely careful* with this command, as it modifies the user's
        #       installed packages, to potentially catastrophic results
        # NOTE: This is not abstracted into another function *on purpose*
        result = subprocess.call(
            [sys.executable, "-m", "pip", "uninstall", "--quiet", "-y", plugin.package_name]
        )
        if not result_handler.handle_uninstall_result(result):
            sys.exit(1)
