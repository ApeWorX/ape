import importlib
import inspect
import os
import sys
import traceback
from contextlib import contextmanager, nullcontext
from importlib.abc import MetaPathFinder
from importlib.machinery import ModuleSpec, PathFinder
from pathlib import Path
from runpy import run_module
from typing import Any

import click

from ape.cli.commands import ConnectedProviderCommand
from ape.cli.options import _VERBOSITY_VALUES, _create_verbosity_kwargs, verbosity_option
from ape.exceptions import ApeException, handle_ape_exception
from ape.logging import logger


class _LocalNamespacePath(list[str]):
    """Fixed namespace search path pinned to a project's `scripts/` directory."""

    def __repr__(self) -> str:
        return f"_NamespacePath({super().__repr__()})"


class _LocalScriptsFinder(MetaPathFinder):
    """Prioritize the project's local `scripts/` directory over any installed `scripts` package."""

    def __init__(self, project_root: Path):
        self.project_root = str(project_root)
        self.project_root_resolved = project_root.resolve()

    def find_spec(self, fullname: str, path: Any = None, target: Any = None) -> ModuleSpec | None:
        if fullname != "scripts":
            return None

        spec = PathFinder.find_spec(fullname, [self.project_root], target)
        if spec is not None and spec.loader is None and spec.submodule_search_locations is not None:
            # Pin namespace search locations to the project's `scripts/` folder so later
            # `sys.path` mutations cannot re-scan into site-packages.
            spec.submodule_search_locations = _LocalNamespacePath(spec.submodule_search_locations)

        return spec


@contextmanager
def use_scripts_sys_path(path: Path):
    # perf: avoid importing at top of module so `--help` is faster.
    from ape.utils.os import use_temp_sys_path

    path_ctx = nullcontext() if str(path) in sys.path else use_temp_sys_path(path)
    scripts_dir = path / "scripts"
    if not scripts_dir.is_dir():
        with path_ctx:
            yield
        return

    resolved_path = path.resolve()
    if any(
        isinstance(f, _LocalScriptsFinder) and f.project_root_resolved == resolved_path
        for f in sys.meta_path
    ):
        with path_ctx:
            yield
        return

    # Temporarily shadow any pre-existing `scripts` package (and submodules) in `sys.modules`
    # and prioritize the project's local `scripts/` directory on `sys.meta_path` so an installed
    # `scripts` package cannot shadow local scripts (including regular vs. namespace precedence).
    saved_modules = {
        name: mod
        for name, mod in list(sys.modules.items())
        if name == "scripts" or name.startswith("scripts.")
    }
    for name in saved_modules:
        sys.modules.pop(name, None)

    finder = _LocalScriptsFinder(path)
    sys.meta_path.insert(0, finder)
    importlib.invalidate_caches()
    try:
        with path_ctx:
            yield
    finally:
        if finder in sys.meta_path:
            sys.meta_path.remove(finder)

        for name in [k for k in list(sys.modules) if k == "scripts" or k.startswith("scripts.")]:
            sys.modules.pop(name, None)

        sys.modules.update(saved_modules)


def get_module(script_path: Path) -> str:
    mod_name = ".".join(
        str(script_path).replace(os.path.sep, ".").split("scripts.")[-1].split(".")[:-1]
    )
    return mod_name if "." in mod_name else f"scripts.{mod_name}"


def run_script_module(script_path: Path):
    mod_name = get_module(script_path)
    return run_module(mod_name)


class ScriptCommand(click.MultiCommand):
    def __init__(self, *args, **kwargs):
        if "result_callback" not in kwargs:
            kwargs["result_callback"] = self.result_callback

        super().__init__(*args, **kwargs)
        self._namespace = {}
        self._command_called = None
        self._has_warned_missing_hook: set[Path] = set()

    def invoke(self, ctx: click.Context) -> Any:
        from ape.utils.basemodel import ManagerAccessMixin as access

        with use_scripts_sys_path(Path.cwd()):
            try:
                return super().invoke(ctx)
            except Exception as err:
                if ctx.params["interactive"]:
                    # Print the exception trace and then launch the console
                    # Attempt to use source-traceback style printing.
                    network_value = (
                        ctx.params.get("network") or access.network_manager.default_ecosystem.name
                    )
                    with access.network_manager.parse_network_choice(
                        network_value, disconnect_on_exit=False
                    ):
                        path = ctx.obj.local_project.path
                        assert isinstance(path, Path)  # For mypy.
                        if not isinstance(err, ApeException) or not handle_ape_exception(
                            err, (path,)
                        ):
                            err_info = traceback.format_exc()
                            click.echo(err_info)

                        self._launch_console()
                else:
                    # Don't handle error - raise exception as normal.
                    raise

    def _get_command(self, filepath: Path) -> click.Command | click.Group | None:
        scripts_folder = Path.cwd() / "scripts"
        relative_filepath = filepath.relative_to(scripts_folder)

        # First load the code module by compiling it
        # NOTE: This does not execute the module
        logger.debug(f"Parsing module: {relative_filepath}")
        try:
            code = compile(filepath.read_text(encoding="utf8"), filepath, "exec")
        except SyntaxError as e:
            logger.error_from_exception(e, f"Exception while parsing script: {relative_filepath}")
            return None  # Prevents stalling scripts

        # NOTE: Introspect code structure only for given patterns (do not execute it to find hooks)
        if "cli" in code.co_names:
            # If the module contains a click cli subcommand, process it and return the subcommand
            logger.debug(f"Found 'cli' command in script: {relative_filepath}")

            with use_scripts_sys_path(filepath.parent.parent):
                try:
                    cli_ns = run_script_module(filepath)
                except Exception as e:  # noqa: BLE001
                    logger.error_from_exception(
                        e, f"Exception while parsing script: {relative_filepath}"
                    )
                    return None  # Prevents stalling scripts

            self._namespace[filepath.stem] = cli_ns
            cli_obj = cli_ns["cli"]
            if not isinstance(cli_obj, click.Command):
                logger.warning("Found `cli()` method but it is not a click command.")
                return None

            params = [getattr(x, "name", None) for x in cli_obj.params]
            if "verbosity" not in params:
                option_kwargs = _create_verbosity_kwargs()
                option = click.Option(_VERBOSITY_VALUES, **option_kwargs)
                cli_obj.params.append(option)

            cli_obj.name = filepath.stem if cli_obj.name in ("cli", "", None) else cli_obj.name
            return cli_obj

        elif "main" in code.co_names:
            logger.debug(f"Found 'main' method in script: {relative_filepath}")

            @click.command(
                cls=ConnectedProviderCommand,
                short_help=f"Run '{relative_filepath}:main'",
                name=relative_filepath.stem,
            )
            @verbosity_option()
            def call(network):
                _ = network  # Downstream might use this
                with use_scripts_sys_path(filepath.parent.parent):
                    main_ns = run_script_module(filepath)
                    self._namespace[filepath.stem] = main_ns
                    main_ns["main"]()  # Execute the script

            return call

        else:
            if relative_filepath not in self._has_warned_missing_hook:
                # Not a script solely to be run by Ape; ignore.
                logger.debug(f"No 'main' method or 'cli' command in script: {relative_filepath}")
                self._has_warned_missing_hook.add(relative_filepath)

            @click.command(
                cls=ConnectedProviderCommand,
                short_help=f"Run '{relative_filepath}:main'",
                name=relative_filepath.stem,
            )
            def call():
                with use_scripts_sys_path(filepath.parent.parent):
                    empty_ns = run_script_module(filepath)

                # Nothing to call, everything executes on loading
                self._namespace[filepath.stem] = empty_ns

            return call

    @property
    def commands(self) -> dict[str, click.Command | click.Group]:
        # perf: Don't reference `.local_project.scripts_folder` here;
        #   it's too slow when doing just doing `--help`.
        scripts_folder = Path.cwd() / "scripts"
        if not scripts_folder.is_dir():
            return {}

        with use_scripts_sys_path(scripts_folder.parent):
            return self._get_cli_commands(scripts_folder)

    def _get_commands(self, ctx: click.Context) -> dict[str, click.Command | click.Group]:
        scripts_folder = Path.cwd() / "scripts"
        cache_key = f"{__name__}.commands:{scripts_folder}"
        if cache_key not in ctx.meta:
            ctx.meta[cache_key] = self.commands

        return ctx.meta[cache_key]

    def _get_cli_commands(self, base_path: Path) -> dict:
        commands: dict[str, click.Command] = {}

        for filepath in base_path.iterdir():
            if filepath.stem.startswith("_"):
                continue  # Ignore any "private" files

            elif filepath.is_dir():
                group = click.Group(
                    name=filepath.stem, short_help=f"Run a script from '{filepath.stem}'"
                )
                subcommands = self._get_cli_commands(filepath)
                for subcommand in subcommands.values():
                    group.add_command(subcommand)

                commands[filepath.stem] = group

            if filepath.suffix == ".py":
                cmd = self._get_command(filepath)
                if cmd:  # NOTE: Don't allow calling commands that failed to load
                    commands[filepath.stem] = cmd

        return commands

    def list_commands(self, ctx):
        return sorted(self._get_commands(ctx))

    def get_command(self, ctx, name):
        if Path(name).exists():
            name = Path(name).stem

        commands = self._get_commands(ctx)
        if name in commands:
            self._command_called = name
            return commands[name]

        # NOTE: don't return anything so Click displays proper error

    def result_callback(self, result, interactive: bool):  # type: ignore[override]
        if interactive:
            return self._launch_console()

        return result

    def _launch_console(self):
        from ape.utils.basemodel import ManagerAccessMixin as access

        trace = inspect.trace()
        trace_frames = [
            x for x in trace if x.filename.startswith(str(access.local_project.scripts_folder))
        ]
        if not trace_frames:
            # Error from Ape internals; avoid launching console.
            sys.exit(1)

        # Use most recently matching frame.
        frame = trace_frames[-1].frame

        try:
            globals_dict = {k: v for k, v in frame.f_globals.items() if not k.startswith("__")}
            extra_locals = {
                **self._namespace.get(self._command_called, {}),
                **globals_dict,
                **frame.f_locals,
            }

        finally:
            # Avoid keeping a reference to a frame to avoid reference cycles.
            if frame:
                del frame

        from ape_console._cli import console

        return console(project=access.local_project, extra_locals=extra_locals, embed=True)


@click.command(
    cls=ScriptCommand,
    short_help="Run scripts from the `scripts/` folder",
)
@click.option(
    "-I",
    "--interactive",
    is_flag=True,
    default=False,
    help="Drop into interactive console session after running",
)
def cli(interactive):
    """
    Run scripts from the "scripts/" folder of a project. A script must either define a ``main()``
    method, or define a command named ``cli`` that is a ``click.Command`` or ``click.Group`` object.
    Scripts with only a ``main()`` method will be called with a network option given to the command.
    Scripts with a ``cli`` command should import any mix-ins necessary to operate from the
    ``ape.cli`` package.
    """
    _ = interactive  # NOTE: Used in above callback handler
