import subprocess
import sys
from pathlib import Path
from typing import Collection, List, Set, Tuple

import click

from ape.cli import ape_cli_context, skip_confirmation_option
from ape.managers.config import CONFIG_FILE_NAME
from ape.plugins import plugin_manager
from ape.utils import github_client, load_config
from ape_plugins.utils import ApePlugin, ModifyPluginResultHandler


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


def plugins_argument():
    """
    An argument that is either the given list of plugins
    or plugins loaded from the local config file.
    """

    def callback(ctx, param, value: Tuple[str]):
        if not value:
            ctx.obj.abort("You must give at least one requirement to install.")

        elif len(value) == 1 and Path(value[0]).resolve().exists():
            # User passed in a path to a config file.
            config_path = Path(value[0]).expanduser().resolve()

            if config_path.name != CONFIG_FILE_NAME:
                config_path = config_path / CONFIG_FILE_NAME
            config = load_config(config_path)
            plugins = config.get("plugins") or []

            if not plugins:
                ctx.obj.logger.warning(f"No plugins found in config '{config_path}'.")
                sys.exit(0)

            return [ApePlugin.from_dict(d) for d in plugins]

        else:
            return [ApePlugin(v) for v in value]

    return click.argument(
        "plugins",
        callback=callback,
        nargs=-1,
        metavar="PLUGIN-NAMES or path/to/project-dir",
    )


def upgrade_option(help: str = "", **kwargs):
    """
    A ``click.option`` for upgrading plugins (``--upgrade``).

    Args:
        help (str): CLI option help text. Defaults to ``""``.
    """

    return click.option("-U", "--upgrade", default=False, is_flag=True, help=help, **kwargs)


@cli.command(name="list")
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
    """Display plugins"""

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

    installed_plugins = []
    if installed_second_class_plugins:
        installed_plugins.append(installed_second_class_plugins)

    if installed_third_class_plugins:
        installed_plugins.append(installed_third_class_plugins)

    if installed_plugins:
        sections["Installed Plugins"] = installed_plugins
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


@cli.command()
@ape_cli_context()
@plugins_argument()
@skip_confirmation_option("Don't ask for confirmation to install the plugins")
@upgrade_option(help="Upgrade the plugin to the newest available version")
def install(cli_ctx, plugins, skip_confirmation, upgrade):
    """Install plugins"""

    failures_occurred = False
    for plugin in plugins:
        if plugin.is_part_of_core:
            cli_ctx.logger.error(f"Cannot install core 'ape' plugin '{plugin.name}'.")
            failures_occurred = True
            continue

        elif plugin.requested_version is not None and upgrade:
            cli_ctx.logger.error(
                f"Cannot use '--upgrade' option when specifying "
                f"a version for plugin '{plugin.name}'."
            )
            failures_occurred = True
            continue

        # if plugin is installed but not a 2nd class. It must be a third party
        elif not plugin.is_installed and not plugin.is_available:
            cli_ctx.logger.warning(f"Plugin '{plugin.name}' is not an trusted plugin.")

        result_handler = ModifyPluginResultHandler(cli_ctx.logger, plugin)
        args = [sys.executable, "-m", "pip", "install", "--quiet"]

        if upgrade:
            cli_ctx.logger.info(f"Upgrading '{plugin.name}'...")
            args.extend(("--upgrade", plugin.package_name))

            version_before = plugin.current_version
            result = subprocess.call(args)
            failures_occurred = result_handler.handle_upgrade_result(result, version_before)

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
            failures_occurred = not result_handler.handle_install_result(result)

        else:
            cli_ctx.logger.warning(
                f"'{plugin.name}' is already installed. Did you mean to include '--upgrade'."
            )

    if failures_occurred:
        sys.exit(1)


@cli.command()
@plugins_argument()
@ape_cli_context()
@skip_confirmation_option("Don't ask for confirmation to install the plugins")
def uninstall(cli_ctx, plugins, skip_confirmation):
    """Uninstall plugins"""

    failures_occurred = False
    did_warn_about_version = False
    for plugin in plugins:
        if plugin.requested_version is not None and not did_warn_about_version:
            cli_ctx.logger.warning("Specifying a version when uninstalling is not necessary.")
            did_warn_about_version = True

        result_handler = ModifyPluginResultHandler(cli_ctx.logger, plugin)

        # if plugin is installed but not a 2nd class. It must be a third party
        if plugin.is_installed and not plugin.is_available:
            cli_ctx.logger.warning(
                f"Plugin '{plugin.name}' is installed but not in available plugins. "
                f"Please uninstall outside of Ape."
            )
            failures_occurred = True
            continue

        # check for installed check the config.yaml
        elif not plugin.is_installed:
            cli_ctx.logger.warning(f"Plugin '{plugin.name}' is not installed.")
            failures_occurred = True
            continue

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
