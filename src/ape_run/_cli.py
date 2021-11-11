import sys
from importlib import import_module
from pathlib import Path

import click

from ape import config
from ape.cli import NetworkBoundCommand, ape_cli_context, network_option
from ape.utils import get_relative_path
from ape_console._cli import console

# TODO: Migrate this to a CLI toolkit under ``ape``


def _run_script(cli_ctx, script_path, interactive=False):
    script_path = get_relative_path(script_path, Path.cwd())
    script_parts = script_path.parts[:-1]

    if any(p == ".." for p in script_parts):
        cli_ctx.abort("Cannot execute script from outside current directory")

    # Add to Python path so we can search for the given script to import
    sys.path.append(str(script_path.parent.resolve()))

    # Load the python module to find our hook functions
    try:
        py_module = import_module(script_path.stem)
    except Exception as err:
        cli_ctx.logger.error_from_exception(err, f"Exception while executing script: {script_path}")
        sys.exit(1)

    finally:
        # Undo adding the path to make sure it's not permanent
        sys.path.remove(str(script_path.parent.resolve()))

    # Execute the hooks
    if hasattr(py_module, "cli"):
        # TODO: Pass context to ``cli`` before calling it
        py_module.cli()

    elif hasattr(py_module, "main"):
        # NOTE: ``main()`` accepts no arguments
        py_module.main()

    else:
        cli_ctx.abort("No `main` or `cli` method detected")

    if interactive:
        return console()


@click.command(cls=NetworkBoundCommand, short_help="Run scripts from the `scripts` folder")
@click.argument("scripts", nargs=-1)
@click.option(
    "-i",
    "--interactive",
    is_flag=True,
    default=False,
    help="Drop into interactive console session after running",
)
@ape_cli_context()
@network_option()
def cli(cli_ctx, scripts, interactive, network):
    """
    NAME - Path or script name (from ``scripts/`` folder)

    Run scripts from the ``scripts`` folder. A script must either define a ``main()`` method,
    or define an import named ``cli`` that is a ``click.Command`` or ``click.Group`` object.
    ``click.Group`` and ``click.Command`` objects will be provided with additional context, which
    will be injected dynamically during script execution. The dynamically injected objects are
    the exports from the ``ape`` top-level package (similar to how the console works)
    """
    if not scripts:
        cli_ctx.abort("Must provide at least one script name or path.")

    scripts_folder = config.PROJECT_FOLDER / "scripts"

    # Generate the lookup based on all the scripts defined in the project's ``scripts/`` folder
    # NOTE: If folder does not exist, this will be empty (same as if there are no files)
    available_scripts = {p.stem: p.resolve() for p in scripts_folder.glob("*.py")}

    for name in scripts:
        if Path(name).exists():
            script_file = Path(name).resolve()

        elif not scripts_folder.exists():
            cli_ctx.abort("No 'scripts/' directory detected to run script.")

        elif name not in available_scripts:
            cli_ctx.abort(f"No script named '{name}' detected in scripts folder.")

        else:
            script_file = available_scripts[name]

        # noinspection PyUnboundLocalVariable
        _run_script(cli_ctx, script_file, interactive)
