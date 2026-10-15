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
from ape.cli.options import _VERBOSITY_VALUES, _create_verbosity_kwargs
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


def _console_locals(raw: dict) -> dict:
    """Filter frame locals to values safe for ``ApeConsoleNamespace``."""
    return {
        k: v
        for k, v in raw.items()
        if k not in {"self", "cls", "args", "kwargs"} and not k.startswith("_")
    }


def wrap_interactive_console(callback: Callable) -> Callable:
    """
    Wrap callback (either ``main()`` from script or ``click.Command.callback``)
    with launching an interactive console on failure or success.
    """

    from ape.utils.basemodel import ManagerAccessMixin as access

    callback_code = getattr(callback, "__code__", None)

    @wraps(callback)
    def wrapper(*args, **kwargs) -> Any:
        result = None
        extra_locals: dict = {}
        captured: dict = {}

        def _local_tracer(frame, event, arg):
            # Only attached to the script callback's frame; grab locals as it returns.
            if event == "return":
                captured.update(frame.f_locals)
            return _local_tracer

        def _tracer(frame, event, arg):
            # Global tracer: only trace the script callback's own frame (success path).
            # Returning None for every other frame avoids line-tracing the whole process.
            if callback_code is not None and frame.f_code is callback_code:
                return _local_tracer
            return None

        try:
            prior_trace = sys.gettrace()
            sys.settrace(_tracer)
            try:
                result = callback(*args, **kwargs)
            finally:
                sys.settrace(prior_trace)

        except Exception as err:  # noqa: BLE001
            extra_locals.update(_console_locals(get_locals_from_trace(inspect.trace())))

            # Print the exception trace and then launch the console
            # Attempt to use source-traceback style printing.
            path = access.local_project.path
            assert isinstance(path, Path)  # For mypy.
            if not isinstance(err, ApeException) or not handle_ape_exception(err, (path,)):
                err_info = traceback.format_exc()
                click.echo(err_info)

        else:  # Function succeeded
            extra_locals.update(_console_locals(captured))

        finally:
            from ape_console._cli import console

            console(extra_locals=extra_locals, embed=True)

        return result

    return wrapper


@contextmanager
def use_scripts_sys_path(path: Path):
    # perf: avoid importing at top of module so `--help` is faster.
    from ape.utils.os import use_temp_sys_path

    # First, ensure there is not an existing scripts module.
    scripts = sys.modules.get("scripts")
    if scripts:
        del sys.modules["scripts"]

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

    if scripts and sys.modules.get("scripts") != scripts:
        sys.modules["scripts"] = scripts


def get_module_name(script_path: Path, scripts_folder: Path) -> str:
    """
    Return a fully-qualified module name under the ``scripts`` namespace.

    Loading as ``scripts.<name>`` (with the project root on ``sys.path``) avoids
    colliding with installed packages that share a script stem (e.g. ``click.py``)
    and preserves relative imports like ``from ._utils import ...``.
    """
    rel = script_path.with_suffix("").relative_to(scripts_folder)
    return "scripts." + ".".join(rel.parts)


def run_script_module(script_path: Path, scripts_folder: Path):
    mod_name = get_module_name(script_path, scripts_folder)
    return run_module(mod_name)


def _ensure_verbosity_option(cli_obj: click.Command) -> None:
    params = [getattr(x, "name", None) for x in cli_obj.params]
    if "verbosity" not in params:
        option_kwargs = _create_verbosity_kwargs()
        option = click.Option(_VERBOSITY_VALUES, **option_kwargs)
        cli_obj.params.append(option)


class MainScript(ConnectedProviderCommand, ManagerAccessMixin):
    """
    A script file that contains a singular ``main()`` method to execute.

    Note: by subclassing ``ConnectedProviderCommand`` we get network auto-loading.
    """

    def __init__(
        self, path: Path, scripts_folder: Path, *args, interactive: bool = False, **kwargs
    ):
        self.path = path
        self.scripts_folder = scripts_folder
        self.interactive = interactive

        if not kwargs.get("help"):
            kwargs["help"] = f"Run '{self.relative_path}:main'"

        def callback(network=None):
            _ = network  # Downstream might use this
            with use_scripts_sys_path(self.scripts_folder.parent):
                main_ns = run_script_module(self.path, self.scripts_folder)
            main_fn = main_ns["main"]
            if self.interactive:
                main_fn = wrap_interactive_console(main_fn)
            main_fn()

        super().__init__(*args, name=path.stem, callback=callback, **kwargs)

    @property
    def relative_path(self) -> Path:
        """Path to script file relative to project root"""

        return self.path.relative_to(self.local_project.path)


class SideEffectScript(ConnectedProviderCommand, ManagerAccessMixin):
    """Script with neither ``main`` nor ``cli``: execute module body on invoke."""

    def __init__(
        self, path: Path, scripts_folder: Path, *args, interactive: bool = False, **kwargs
    ):
        self.path = path
        self.scripts_folder = scripts_folder
        self.interactive = interactive

        if not kwargs.get("help"):
            kwargs["help"] = f"Run '{self.relative_path}'"

        def callback(network=None):
            _ = network

            def run():
                with use_scripts_sys_path(self.scripts_folder.parent):
                    run_script_module(self.path, self.scripts_folder)

            if self.interactive:
                wrap_interactive_console(run)()
            else:
                run()

        super().__init__(*args, name=path.stem, callback=callback, **kwargs)

    @property
    def relative_path(self) -> Path:
        return self.path.relative_to(self.local_project.path)


ScriptCommand = click.Group | click.Command | MainScript | SideEffectScript


def extract_python_command(
    script_path: Path, scripts_folder: Path, interactive: bool = False
) -> ScriptCommand | None:
    relative_filepath = script_path.relative_to(scripts_folder)

    # First load the code module by compiling it
    # NOTE: This does not execute the module
    logger.debug(f"Parsing module: {relative_filepath}")
    try:
        code = compile(script_path.read_text(encoding="utf8"), script_path, "exec")
    except SyntaxError as e:
        logger.error_from_exception(e, f"Exception while parsing script: {relative_filepath}")
        return None  # Prevents stalling scripts

    # NOTE: Introspect code structure only for given patterns (do not execute it to find hooks)
    if "cli" in code.co_names:
        # If the module contains a click cli subcommand, process it and return the subcommand
        logger.debug(f"Found 'cli' command in script: {relative_filepath}")

        with use_scripts_sys_path(scripts_folder.parent):
            try:
                cli_ns = run_script_module(script_path, scripts_folder)
            except Exception as e:  # noqa: BLE001
                logger.error_from_exception(
                    e, f"Exception while parsing script: {relative_filepath}"
                )
                return None  # Prevents stalling scripts

        cli_obj = cli_ns.get("cli")
        if not isinstance(cli_obj, click.Command):
            logger.warning("Found `cli()` method but it is not a click command.")
            return None

        _ensure_verbosity_option(cli_obj)
        cli_obj.name = script_path.stem if cli_obj.name in ("cli", "", None) else cli_obj.name

        if interactive:
            if isinstance(cli_obj, click.Group):
                for cmd_name, cmd in cli_obj.commands.items():
                    if cmd.callback:
                        logger.debug(
                            f"Wrapping '{cmd_name}' callback from '{script_path.name}:cli'"
                        )
                        cmd.callback = wrap_interactive_console(cmd.callback)
            elif cli_obj.callback:
                logger.debug(f"Wrapping 'cli' callback from '{script_path.name}'")
                cli_obj.callback = wrap_interactive_console(cli_obj.callback)

        return cli_obj

    elif "main" in code.co_names:
        logger.debug(f"Found 'main' method in script: {relative_filepath}")
        return MainScript(script_path, scripts_folder, interactive=interactive)

    else:
        # Not a script solely to be run by Ape; still allow module-level execution on invoke.
        logger.debug(f"No 'main' method or 'cli' command in script: {relative_filepath}")
        return SideEffectScript(script_path, scripts_folder, interactive=interactive)


class ScriptSubfolder(click.Group, ManagerAccessMixin):
    """
    If there is a folder under ``scripts/`` (or recursively under those),
    this command group represents executing scripts from those files.
    """

    def __init__(self, path: Path, *args, interactive: bool = False, **kwargs):
        self.path = path
        self.interactive = interactive

        if not kwargs.get("help"):
            if (readme_file := path / "README.md").exists():
                kwargs["help"] = readme_file.read_text()
            else:
                kwargs["help"] = f"Run script(s) from '{path.name}'"

        super().__init__(*args, **kwargs)

    @property
    def relative_path(self) -> Path:
        """Path to folder relative to project root"""

        return self.path.relative_to(self.local_project.path)

    @property
    def scripts_folder(self) -> Path:
        return self.local_project.scripts_folder

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} path={self.relative_path}>"

    def list_commands(self, ctx: click.Context) -> list[str]:
        if not self.path.exists():
            return []

        # NOTE: Skip "private" modules/folders
        return sorted(path.stem for path in self.path.iterdir() if not path.stem.startswith("_"))

    def get_command(
        self, ctx: click.Context, cmd_name: str
    ) -> "ScriptSubfolder | ScriptCommand | None":
        # TODO: Run remote scripts? (seems bad)
        # TODO: Run scripts from dependencies?

        interactive = ctx.params.get("interactive", self.interactive)

        if (path := self.path / cmd_name).is_dir() and not (path / "__init__.py").exists():
            # NOTE: `path` is a non-module folder
            logger.debug(
                f"Parsing as script-containing subfolder: '{self.relative_path}/{path.name}'"
            )
            return ScriptSubfolder(path, name=cmd_name, interactive=interactive)

        elif path.is_dir() and (path / "__init__.py").exists():
            # NOTE: `path` is a Python package module
            logger.debug(f"Parsing as script-containing module: '{self.relative_path}/{path.name}'")
            return extract_python_command(path, self.scripts_folder, interactive=interactive)

        elif (path := self.path / f"{cmd_name}.py").exists():
            logger.debug(f"Parsing as script-containing module: '{self.relative_path}/{path.name}'")
            return extract_python_command(path, self.scripts_folder, interactive=interactive)

        # TODO: Non-python scripts? (e.g. smart contract scripts a la Foundry)
        # for ext in self.compiler_manager.registered_compilers:
        #     if (path := self.path / f"{cmd_name}{ext}").exists():
        #        return ContractScript(path, interactive=ctx.params.get("interactive"))

        # NOTE: This shouldn't actually happen if you use one of `.list_commands(ctx)`
        return None  # Click will display error about "command not available"


class ScriptManager(ScriptSubfolder):
    def __init__(self, *args, **kwargs):
        # perf: prefer cwd/scripts for --help speed when possible; fall back to project.
        scripts_folder = Path.cwd() / "scripts"
        if not scripts_folder.is_dir():
            scripts_folder = self.local_project.scripts_folder
        super().__init__(scripts_folder, *args, **kwargs)


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
