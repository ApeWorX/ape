import sys
from importlib import import_module
from pathlib import Path

import click

from ape import config, networks
from ape.utils import Abort, get_relative_path
from ape_console._cli import NetworkChoice, console

# TODO: Migrate this to a CLI toolkit under `ape`


def _run_script(script_path, interactive=False, verbose=False):
    script_path = get_relative_path(script_path, Path.cwd())
    script_parts = script_path.parts[:-1]

    if any(p == ".." for p in script_parts):
        raise Abort("Cannot execute script from outside current directory")

    # Add to Python path so we can search for the given script to import
    sys.path.append(str(script_path.parent.resolve()))

    # Load the python module to find our hook functions
    try:
        py_module = import_module(script_path.stem)

    except Exception as e:
        if verbose:
            raise e

        else:
            raise Abort(f"Exception while executing script: {script_path}") from e

    finally:
        # Undo adding the path to make sure it's not permanent
        sys.path.remove(str(script_path.parent.resolve()))

    # Execute the hooks
    if hasattr(py_module, "cli"):
        # TODO: Pass context to `cli` before calling it
        py_module.cli()

    elif hasattr(py_module, "main"):
        # NOTE: `main()` accepts no arguments
        py_module.main()

    else:
        raise Abort("No `main` or `cli` method detected")

    if interactive:
        return console()


@click.command(short_help="Run scripts from the `scripts` folder")
@click.argument("scripts", nargs=-1)
@click.option(
    "-v",
    "--verbose",
    is_flag=True,
    default=False,
    help="Display errors from scripts",
)
@click.option(
    "-i",
    "--interactive",
    is_flag=True,
    default=False,
    help="Drop into interactive console session after running",
)
@click.option(
    "--network",
    type=NetworkChoice(case_sensitive=False),
    default=networks.default_ecosystem.name,
    help="Override the default network and provider. (see `ape networks list` for options)",
    show_default=True,
    show_choices=False,
)
def cli(scripts, verbose, interactive, network):
    """
    NAME - Path or script name (from `scripts/` folder)

    Run scripts from the `scripts` folder. A script must either define a `main()` method,
    or define an import named `cli` that is a `click.Command` or `click.Group` object.
    `click.Group` and `click.Command` objects will be provided with additional context, which
    will be injected dynamically during script execution. The dynamically injected objects are
    the exports from the `ape` top-level package (similar to how the console works)
    """
    if not scripts:
        raise Abort("Must provide at least one script name or path")

    scripts_folder = config.PROJECT_FOLDER / "scripts"

    # Generate the lookup based on all the scripts defined in the project's `scripts/` folderi
    # NOTE: If folder does not exist, this will be empty (same as if there are no files)
    available_scripts = {p.stem: p.resolve() for p in scripts_folder.glob("*.py")}

    with networks.parse_network_choice(network):
        for name in scripts:
            if Path(name).exists():
                script_file = Path(name).resolve()

            elif not scripts_folder.exists():
                raise Abort("No `scripts/` directory detected to run script")

            elif name not in available_scripts:
                raise Abort(f"No script named '{name}' detected in scripts folder")

            else:
                script_file = available_scripts[name]

            _run_script(script_file, interactive, verbose)
