import subprocess
import sys
from pathlib import Path
from typing import List, Tuple

import click

from ape.cli import ape_cli_context, skip_confirmation_option
from ape.managers.config import CONFIG_FILE_NAME
from ape.utils import github_client, load_config
from ape_plugins.utils import (
    ModifyPluginResultHandler,
    PluginMetadata,
    PluginMetadataList,
    PluginType,
)


@click.group(short_help="Manage ape plugins")
def cli():
    """
    Command-line helper for managing plugins.
    """


def plugins_argument():
    """
    An argument that is either the given list of plugins
    or plugins loaded from the local config file.
    """

    def load_from_file(ctx, file_path: Path) -> List[PluginMetadata]:
        if file_path.is_dir() and (file_path / CONFIG_FILE_NAME).is_file():
            file_path = file_path / CONFIG_FILE_NAME

        if file_path.is_file():
            config = load_config(file_path)
            if plugins := config.get("plugins"):
                return [PluginMetadata.parse_obj(d) for d in plugins]

        ctx.obj.logger.warning(f"No plugins found at '{file_path}'.")
        return []

    def callback(ctx, param, value: Tuple[str]):
        if not value:
            ctx.obj.abort("You must give at least one requirement to install.")

        elif len(value) == 1:
            # User passed in a path to a file.
            file_path = Path(value[0]).expanduser().resolve()
            return (
                load_from_file(ctx, file_path)
                if file_path.exists()
                else [PluginMetadata(name=v) for v in value[0].split(" ")]
            )

        else:
            return [PluginMetadata(name=v) for v in value]

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


def _display_all_callback(ctx, param, value):
    return (
        (PluginType.CORE, PluginType.INSTALLED, PluginType.THIRD_PARTY, PluginType.AVAILABLE)
        if value
        else (PluginType.INSTALLED, PluginType.THIRD_PARTY)
    )


@cli.command(name="list", short_help="Display plugins")
@click.option(
    "-a",
    "--all",
    "to_display",
    default=False,
    is_flag=True,
    callback=_display_all_callback,
    help="Display all plugins installed and available (including Core)",
)
@ape_cli_context()
def _list(cli_ctx, to_display):
    registered_plugins = cli_ctx.plugin_manager.registered_plugins
    available_plugins = github_client.available_plugins
    metadata = PluginMetadataList.from_package_names(registered_plugins.union(available_plugins))
    if output := metadata.to_str(include=to_display):
        click.echo(output)
        if not metadata.installed and not metadata.third_party:
            click.echo("No plugins installed (besides core plugins).")

    else:
        click.echo("No plugins installed.")


@cli.command()
@ape_cli_context()
@plugins_argument()
@skip_confirmation_option("Don't ask for confirmation to install the plugins")
@upgrade_option(help="Upgrade the plugin to the newest available version")
def install(cli_ctx, plugins, skip_confirmation, upgrade):
    """Install plugins"""

    failures_occurred = False
    for plugin in plugins:
        if plugin.in_core:
            cli_ctx.logger.error(f"Cannot install core 'ape' plugin '{plugin.name}'.")
            failures_occurred = True
            continue

        elif plugin.version is not None and upgrade:
            cli_ctx.logger.error(
                f"Cannot use '--upgrade' option when specifying "
                f"a version for plugin '{plugin.name}'."
            )
            failures_occurred = True
            continue

        # if plugin is installed but not trusted. It must be a third party
        elif plugin.is_third_party:
            cli_ctx.logger.warning(f"Plugin '{plugin.name}' is not an trusted plugin.")

        result_handler = ModifyPluginResultHandler(plugin)
        pip_arguments = [sys.executable, "-m", "pip", "install"]

        if upgrade:
            cli_ctx.logger.info(f"Upgrading '{plugin.name}'...")
            pip_arguments.extend(("--upgrade", plugin.package_name))

            version_before = plugin.current_version

            # NOTE: There can issues when --quiet is not at the end.
            pip_arguments.append("--quiet")

            result = subprocess.call(pip_arguments)

            # Returns ``True`` when upgraded successfully
            failures_occurred = not result_handler.handle_upgrade_result(result, version_before)

        elif plugin.can_install and (
            plugin.is_available
            or skip_confirmation
            or click.confirm(f"Install the '{plugin.name}' plugin?")
        ):
            cli_ctx.logger.info(f"Installing {plugin}...")

            # NOTE: There can issues when --quiet is not at the end.
            pip_arguments.extend((plugin.install_str, "--quiet"))

            # NOTE: Be *extremely careful* with this command, as it modifies the user's
            #       installed packages, to potentially catastrophic results
            # NOTE: This is not abstracted into another function *on purpose*
            result = subprocess.call(pip_arguments)
            failures_occurred = not result_handler.handle_install_result(result)

        else:
            cli_ctx.logger.warning(
                f"'{plugin.name}' is already installed. " f"Did you mean to include '--upgrade'."
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
        if plugin.version is not None and not did_warn_about_version:
            cli_ctx.logger.warning("Specifying a version when uninstalling is not necessary.")
            did_warn_about_version = True

        result_handler = ModifyPluginResultHandler(plugin)

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
            args = [sys.executable, "-m", "pip", "uninstall", "-y", plugin.package_name, "--quiet"]

            # NOTE: Be *extremely careful* with this command, as it modifies the user's
            #       installed packages, to potentially catastrophic results
            # NOTE: This is not abstracted into another function *on purpose*
            result = subprocess.call(args)
            failures_occurred = not result_handler.handle_uninstall_result(result)

    if failures_occurred:
        sys.exit(1)
