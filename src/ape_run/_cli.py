from pathlib import Path

import click

from ape import config
from ape.utils import Abort


def _run_script(script_file, interactive=False):
    # Load the python module and find our hook functions
    ns: dict = {}
    try:
        py_module = compile(script_file.read_text(), str(script_file), "exec")
        eval(py_module, ns, ns)

    except Exception as e:
        raise Abort(e.with_traceback()) from e

    # Execute the hooks
    if "cli" in ns:
        # TODO: Pass context to `cli` before calling it
        ns["cli"]()

    elif "main" in ns:
        # NOTE: `main()` accepts no arguments
        ns["main"]()

    else:
        raise Abort("No `main` or `cli` method detected")

    if interactive:
        pass  # run console w/ `ns` from running script


@click.command(short_help="Run scripts from the `scripts` folder")
@click.argument("scripts", nargs=-1)
@click.option("-i", "--interactive", help="Drop into interactive console session after running")
def cli(scripts, interactive):
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
    available_scripts = {p.stem: p for p in scripts_folder.glob("*.py")}

    for name in scripts:
        if Path(name).exists():
            # NOTE: This injects the path as the only option (bypassing the lookup)
            script_file = Path(name)

        elif not scripts_folder.exists():
            raise Abort("No `scripts/` directory detected to run script")

        elif name not in available_scripts:
            raise Abort(f"No script named '{name}' detected in scripts folder")

        else:
            script_file = available_scripts[name]

        _run_script(script_file, interactive)
