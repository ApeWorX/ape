import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Tuple

import click
from packaging.version import Version

from ape.cli import ape_cli_context, skip_confirmation_option
from ape.logging import logger
from ape.managers.config import CONFIG_FILE_NAME
from ape.plugins._utils import (
    ModifyPluginResultHandler,
    PluginMetadata,
    PluginMetadataList,
    PluginType,
    _pip_freeze,
    ape_version,
)
from ape.utils import load_config


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
                res = [PluginMetadata.model_validate(d) for d in plugins]
                for itm in res:
                    itm._use_subprocess_pip_freeze = True

                return res

        ctx.obj.logger.warning(f"No plugins found at '{file_path}'.")
        return []

    def callback(ctx, param, value: Tuple[str]):
        res = []
        if not value:
            ctx.obj.abort("You must give at least one requirement to install.")

        elif len(value) == 1:
            # User passed in a path to a file.
            file_path = Path(value[0]).expanduser().resolve()
            res = (
                load_from_file(ctx, file_path)
                if file_path.exists()
                else [
                    PluginMetadata(name=v, _use_subprocess_pip_freeze=True)
                    for v in value[0].split(" ")
                ]
            )

        else:
            res = [PluginMetadata(name=v, _use_subprocess_pip_freeze=True) for v in value]

        for itm in res:
            itm._use_subprocess_pip_freeze = True

        return res

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
    metadata = PluginMetadataList.load(cli_ctx.plugin_manager)
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
def install(cli_ctx, plugins: List[PluginMetadata], skip_confirmation: bool, upgrade: bool):
    """Install plugins"""

    failures_occurred = False

    # Track the operations until the end. This way, if validation
    # fails on one, we can error-out before installing anything.
    install_list: List[Dict[str, Any]] = []

    for plugin in plugins:
        result = plugin._prepare_install(upgrade=upgrade, skip_confirmation=skip_confirmation)
        if result:
            install_list.append(result)
        else:
            failures_occurred = True

    # NOTE: Be *extremely careful* with `subprocess.call`, as it modifies the user's
    #       installed packages, to potentially catastrophic results
    for op in install_list:
        if not op:
            continue

        handler = op["result_handler"]
        call_result = subprocess.call(op["args"])
        if "version_before" in op:
            success = not handler.handle_upgrade_result(call_result, op["version_before"])
            failures_occurred = not failures_occurred and success

        else:
            success = not handler.handle_install_result(call_result)
            failures_occurred = not failures_occurred and success

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


@cli.command()
def update():
    """
    Update Ape and all plugins to the next version
    """

    _change_version(ape_version.next_version_range)


def _version_callack(ctx, param, value):
    obj = Version(value)
    version_str = f"0.{obj.minor}.0" if obj.major == 0 else f"{obj.major}.0.0"
    return f"=={version_str}"


@cli.command()
@click.argument("version", callback=_version_callack)
def change_version(version):
    """
    Change ape and all plugins version
    """

    _change_version(version)


def _change_version(spec: str):
    # Update all the plugins.
    # This will also update core Ape.
    # NOTE: It is possible plugins may depend on each other and may update in
    #   an order causing some error codes to pop-up, so we ignore those for now.
    for plugin in _pip_freeze.get_plugins(use_process=True):
        logger.info(f"Updating {plugin} ...")
        name = plugin.split("=")[0].strip()
        subprocess.call([sys.executable, "-m", "pip", "install", f"{name}{spec}", "--quiet"])

    # This check is for verifying the update and shouldn't actually do anything.
    logger.info("Updating Ape core ...")
    completed_process = subprocess.run(
        [sys.executable, "-m", "pip", "install", f"eth-ape{spec}", "--quiet"]
    )
    if completed_process.returncode != 0:
        message = "Update failed"
        if output := completed_process.stdout:
            message = f"{message}: {output.decode('utf8')}"

        logger.error(message)
        sys.exit(completed_process.returncode)

    else:
        logger.success("Ape and all plugins have successfully upgraded.")
