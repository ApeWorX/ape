from pathlib import Path

import click

from ape.utils import Abort, notify


def _run_script(scripts_folder, name, interactive=False):
    if Path(name).exists():
        # NOTE: This injects the path as the only option (bypassing the lookup)
        script_file = Path(name)

    else:  # We're using the short name, so generate the lookup table of all scripts in project
        # NOTE: Generate the lookup based on all the scripts defined in the project
        found_name = False
        for script_file in scripts_folder.glob("*.py"):
            if script_file.stem == name:
                found_name = True
                break  # NOTE: `script_file` is set

        if not found_name:
            raise Abort(f"No script named '{name}' detected in scripts folder")

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
        return ns["cli"]()

    elif "main" in ns:
        # NOTE: `main()` accepts no arguments
        return ns["main"]()

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
    from ape import config

    scripts_folder = config.PROJECT_FOLDER / "scripts"
    if not scripts_folder.exists():
        notify("WARNING", "No `scripts/` directory detected")
        return

    if len(scripts) == 0:
        raise Abort("Must provide at least one script name or path")

    for name in scripts:
        _run_script(scripts_folder, name, interactive)
