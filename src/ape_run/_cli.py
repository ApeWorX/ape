import inspect
import sys
import traceback
from collections.abc import Callable
from contextlib import contextmanager
from functools import wraps
from pathlib import Path
from runpy import run_module
from typing import Any

import click

from ape.cli.commands import ConnectedProviderCommand
from ape.exceptions import ApeException, handle_ape_exception
from ape.logging import logger
from ape.utils.basemodel import ManagerAccessMixin


def get_locals_from_trace(trace):
    from ape.utils.basemodel import ManagerAccessMixin as access

    extra_locals = {}
    trace_frames = [
        x for x in trace if x.filename.startswith(str(access.local_project.scripts_folder))
    ]
    if not trace_frames:
        # Error from Ape internals; avoid launching console.
        sys.exit(1)

    # Use most recently matching frame.
    frame = trace_frames[-1].frame

    extra_locals.update({k: v for k, v in frame.f_globals.items() if not k.startswith("_")})
    extra_locals.update(frame.f_locals)

    # Avoid keeping a reference to a frame to avoid reference cycles.
    del frame

    return extra_locals


def wrap_interactive_console(callback: Callable) -> Callable:
    """
    Wrap callback (either `main()` from script or `click.Command.callback`)
    with launching an interactive console on failure or success.
    """

    from ape.utils.basemodel import ManagerAccessMixin as access

    @wraps(callback)
    def wrapper(*args, **kwargs) -> Any:
        result = None
        extra_locals: dict = {}

        try:
            result = callback(*args, **kwargs)
            frame = inspect.currentframe()

        except Exception as err:
            extra_locals.update(get_locals_from_trace(inspect.trace()))

            # Print the exception trace and then launch the console
            # Attempt to use source-traceback style printing.
            assert isinstance(path := access.local_project.path, Path)  # For mypy.
            if not isinstance(err, ApeException) or not handle_ape_exception(err, (path,)):
                err_info = traceback.format_exc()
                click.echo(err_info)

        else:  # Function succeeded
            if frame and frame.f_back:
                extra_locals.update(frame.f_back.f_locals)

        finally:
            from ape_console._cli import console

            console(extra_locals=extra_locals, embed=True)

        return result

    return wrapper


class MainScript(ConnectedProviderCommand, ManagerAccessMixin):
    """
    A script file that contains a singular `main()` method to execute.

    Note: by subclassing `ConnectedProviderCommand` we get network auto-loading.
    """

    def __init__(self, path: Path, callback: Callable[[], None], *args, **kwargs):
        self.path = path

        if not kwargs.get("help"):
            kwargs["help"] = callback.__doc__ or f"Run '{self.relative_path}:{callback.__name__}'"

        super().__init__(*args, name=path.stem, callback=callback, **kwargs)

    @property
    def relative_path(self) -> Path:
        """Path to script file relative to project root"""

        return self.path.relative_to(self.local_project.path)


ScriptCommand = click.Group | click.Command | MainScript


@contextmanager
def use_temp_sys_path(path: Path):
    # perf: avoid importing at top of module so `--help` is faster.
    from ape.utils.os import use_temp_sys_path

    # First, ensure there is not an existing scripts module.
    if scripts := sys.modules.get(path.stem):
        del sys.modules[path.stem]

        # Sometimes, an installed module is somehow missing a __file__
        # and mistaken by Python to be a system module. We can handle
        # that by also checking some internal properties for the right path.
        excl_paths = (
            [Path(scripts.__file__).parent]
            if scripts.__file__
            else [
                Path(p).parent
                for p in getattr(getattr(scripts, "__path__", None), "_path", []) or []
            ]
        )

    else:
        excl_paths = None

    with use_temp_sys_path(path, exclude=excl_paths):
        yield

    if scripts and sys.modules.get(path.stem) != scripts:
        sys.modules[path.stem] = scripts


def extract_python_command(script_path: Path, interactive: bool = False) -> ScriptCommand | None:
    try:
        with use_temp_sys_path(script_path.parent):
            mod_ns = run_module(script_path.stem)

    except Exception as e:
        logger.error_from_exception(e, f"Exception while parsing script: '{script_path.name}'")

        if interactive:
            extra_locals = get_locals_from_trace(inspect.trace())

            from ape_console._cli import console

            console(extra_locals=extra_locals, embed=True)

        return None  # Will raise "no command named" exception

    if main_fn := mod_ns.get("main"):
        logger.debug(f"Found 'main' method in script: '{script_path.name}'")

        if interactive:
            main_fn = wrap_interactive_console(main_fn)

        cli: ScriptCommand | None = MainScript(script_path, callback=main_fn)
        # NOTE: Added type hint here to avoid issue w/ next line

    elif isinstance(cli := mod_ns.get("cli"), click.Group):
        logger.debug(f"Found 'cli' group in script: '{script_path.name}'")

        if interactive:
            for cmd_name, cmd in cli.commands.items():
                if cmd.callback:
                    logger.debug(f"Wrapping '{cmd_name}' callback from '{script_path.name}:cli'")
                    cmd.callback = wrap_interactive_console(cmd.callback)

    elif isinstance(cli := mod_ns.get("cli"), click.Command):
        logger.debug(f"Found 'cli' command in script: '{script_path.name}'")

        if interactive and cli.callback:
            logger.debug(f"Wrapping 'cli' callback from '{script_path.name}'")
            cli.callback = wrap_interactive_console(cli.callback)

    else:
        logger.warning(
            f"No 'main' function or 'cli' `click.Command|Group` in script: '{script_path.name}'"
        )
        return None  # Click will display error

    return cli


class ScriptSubfolder(click.Group, ManagerAccessMixin):
    """
    If there is a folder under `scripts/` (or recursively under those),
    this command group represents executing scripts from those files.
    """

    def __init__(self, path: Path, *args, interactive: bool = False, **kwargs):
        self.path = path
        self.interactive = interactive

        if not kwargs.get("help"):
            if (readme_file := path / "README.md").exists():
                kwargs["help"] = readme_file.read_text()
            else:
                kwargs["help"] = f"Run script(s) from '{self.relative_path}'"

        super().__init__(*args, **kwargs)

    @property
    def relative_path(self) -> Path:
        """Path to folder relative to project root"""

        return self.path.relative_to(self.local_project.path)

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} path={self.relative_path}>"

    def list_commands(self, ctx: click.Context) -> list[str]:
        if not self.path.exists():
            return []

        # NOTE: Skip "private" modules/folders
        return [path.stem for path in self.path.iterdir() if not path.stem.startswith("_")]

    def get_command(
        self, ctx: click.Context, cmd_name: str
    ) -> "ScriptSubfolder | ScriptCommand | None":
        # TODO: Run remote scripts? (seems bad)
        # TODO: Run scripts from dependencies?

        if (path := self.path / cmd_name).is_dir() and not (path / "__init__.py").exists():
            # NOTE: `path` is a non-module folder
            logger.debug(
                f"Parsing as script-containing subfolder: '{self.relative_path}/{path.name}'"
            )
            return ScriptSubfolder(
                path, interactive=ctx.params.get("interactive", self.interactive)
            )

        elif path.exists() or (path := self.path / f"{cmd_name}.py").exists():
            # NOTE: `path` is either a Python module (containing `__init__.py`) or .py file
            logger.debug(f"Parsing as script-containing module: '{self.relative_path}/{path.name}'")
            return extract_python_command(
                path, interactive=ctx.params.get("interactive", self.interactive)
            )

        # TODO: Non-python scripts? (e.g. smart contract scripts a la Foundry)
        # for ext in self.compiler_manager.registered_compilers:
        #     if (path := self.path / f"{cmd_name}{ext}").exists():
        #        return ContractScript(path, interactive=ctx.params.get("interactive"))

        # NOTE: This shouldn't actually happen if you use one of `.list_commands(ctx)`
        return None  # Click will display error about "command not available"


class ScriptManager(ScriptSubfolder):
    def __init__(self, *args, **kwargs):
        super().__init__(self.local_project.scripts_folder, *args, **kwargs)


# TODO: Script testing pytest plugin?


@click.command(
    cls=ScriptManager,
    short_help="Run scripts from the `scripts/` folder",
)
@click.option(
    "-I",
    "--interactive",
    is_flag=True,
    default=False,
    help="Drop into interactive console session after running",
)
def cli(**_):  # NOTE: options get used from context
    """
    Run scripts from the "scripts/" folder of a project.

    A script must either define a ``main()`` method, or define a command named ``cli`` that is a
    ``click.Command`` or ``click.Group`` object. Scripts with only a ``main()`` method will be
    called with a network option given to the command. Scripts with a ``cli`` command should
    import any mix-ins necessary to operate from the ``ape.cli`` package.
    """
