import inspect
import os
import sys
import traceback
from pathlib import Path
from runpy import run_module
from typing import Any, Dict, Union

import click
from click import Command, Context

from ape.cli import NetworkBoundCommand, network_option
from ape.logging import logger
from ape.managers.project import ProjectManager
from ape.utils import cached_property, get_relative_path, use_temp_sys_path
from ape_console._cli import console


class ScriptCommand(click.MultiCommand):
    def __init__(self, *args, **kwargs):
        if "result_callback" not in kwargs:
            kwargs["result_callback"] = self.result_callback

        super().__init__(*args, **kwargs)
        self._namespace = {}
        self._command_called = None

    def invoke(self, ctx: Context) -> Any:
        try:
            return super().invoke(ctx)
        except Exception:
            if ctx.params["interactive"]:
                # Print the exception trace and then launch the console
                err_info = traceback.format_exc()
                click.echo(err_info)
                self._launch_console()
            else:
                # Don't handle error - raise exception as normal.
                raise

    def _get_command(self, filepath: Path) -> Union[click.Command, click.Group, None]:
        relative_filepath = get_relative_path(filepath, self._project.path)

        # First load the code module by compiling it
        # NOTE: This does not execute the module
        logger.debug(f"Parsing module: {relative_filepath}")
        try:
            code = compile(filepath.read_text(), filepath, "exec")
        except SyntaxError as e:
            logger.error_from_exception(e, f"Exception while parsing script: {relative_filepath}")
            return None  # Prevents stalling scripts

        def _module_str(_filepath: Path) -> str:
            suffix = ".".join(
                (str(_filepath).replace(os.path.sep, ".").split("scripts.")[-1].split(".")[:-1])
            )
            if "." not in suffix:
                return f"scripts.{suffix}"
            else:
                return suffix

        # NOTE: Introspect code structure only for given patterns (do not execute it to find hooks)
        if "cli" in code.co_names:
            # If the module contains a click cli subcommand, process it and return the subcommand
            logger.debug(f"Found 'cli' command in script: {relative_filepath}")

            with use_temp_sys_path(filepath.parent.parent):
                try:
                    cli_ns = run_module(_module_str(filepath))
                except Exception as e:
                    logger.error_from_exception(
                        e, f"Exception while parsing script: {relative_filepath}"
                    )
                    return None  # Prevents stalling scripts

            self._namespace[filepath.stem] = cli_ns
            cli_obj = cli_ns["cli"]
            if not isinstance(cli_obj, Command):
                logger.warning("Found `cli()` method but it is not a click command.")
                return None

            cli_obj.name = filepath.stem if cli_obj.name in ("cli", "", None) else cli_obj.name
            return cli_obj

        elif "main" in code.co_names:
            logger.debug(f"Found 'main' method in script: {relative_filepath}")

            @click.command(
                cls=NetworkBoundCommand,
                short_help=f"Run '{relative_filepath}:main'",
                name=relative_filepath.stem,
            )
            @network_option()
            def call(network):
                _ = network  # Downstream might use this
                with use_temp_sys_path(filepath.parent.parent):
                    main_ns = run_module(_module_str(filepath))

                main_ns["main"]()  # Execute the script
                self._namespace[filepath.stem] = main_ns

            return call

        else:
            logger.warning(f"No 'main' method or 'cli' command in script: {relative_filepath}")

            @click.command(
                cls=NetworkBoundCommand,
                short_help=f"Run '{relative_filepath}:main'",
                name=relative_filepath.stem,
            )
            @network_option()
            def call(network):
                _ = network  # Downstream might use this
                with use_temp_sys_path(filepath.parent.parent):
                    empty_ns = run_module(_module_str(filepath))

                # Nothing to call, everything executes on loading
                self._namespace[filepath.stem] = empty_ns

            return call

    @cached_property
    def _project(self) -> ProjectManager:
        """
        A class representing the project that is active at runtime.
        (This is the same object as from ``from ape import project``).

        Returns:
            :class:`~ape.managers.project.ProjectManager`
        """

        from ape import project

        project.config_manager.load()

        return project

    @cached_property
    def commands(self) -> Dict[str, Union[click.Command, click.Group]]:
        if not self._project.scripts_folder.exists():
            return {}

        return self._get_cli_commands(self._project.scripts_folder)

    def _get_cli_commands(self, base_path: Path) -> Dict:
        commands: Dict[str, Command] = {}

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
        return list(sorted(self.commands))

    def get_command(self, ctx, name):
        if Path(name).exists():
            name = Path(name).stem

        if name in self.commands:
            self._command_called = name
            return self.commands[name]

        # NOTE: don't return anything so Click displays proper error

    def result_callback(self, result, interactive):
        if interactive:
            return self._launch_console()

        return result

    def _launch_console(self):
        trace = inspect.trace()
        trace_frames = [
            x for x in trace if x.filename.startswith(str(self._project.scripts_folder))
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

        return console(project=self._project, extra_locals=extra_locals)


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
