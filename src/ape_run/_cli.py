from pathlib import Path
from runpy import run_module
from typing import Dict, Union

import click

from ape.cli import NetworkBoundCommand, network_option
from ape.logging import logger
from ape.managers.project import ProjectManager
from ape.utils import cached_property, get_relative_path, use_temp_sys_path
from ape_console._cli import console


class ScriptCommand(click.MultiCommand):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs, result_callback=self.result_callback)
        self._namespace = {}

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

        # NOTE: Introspect code structure only for given patterns (do not execute it to find hooks)
        if "cli" in code.co_names:
            # If the module contains a click cli subcommand, process it and return the subcommand
            logger.debug(f"Found 'cli' command in script: {relative_filepath}")

            with use_temp_sys_path(filepath.parent.parent):
                try:
                    ns = run_module(f"scripts.{filepath.stem}")
                except Exception as e:
                    logger.error_from_exception(
                        e, f"Exception while parsing script: {relative_filepath}"
                    )
                    return None  # Prevents stalling scripts

            self._namespace[filepath.stem] = ns
            return ns["cli"]

        elif "main" in code.co_names:
            logger.debug(f"Found 'main' method in script: {relative_filepath}")

            @click.command(cls=NetworkBoundCommand, short_help=f"Run '{relative_filepath}:main'")
            @network_option()
            def call(network):
                _ = network  # Downstream might use this
                with use_temp_sys_path(filepath.parent.parent):
                    ns = run_module(f"scripts.{filepath.stem}")

                ns["main"]()  # Execute the script
                self._namespace[filepath.stem] = ns

            return call

        else:
            logger.warning(f"No 'main' method or 'cli' command in script: {relative_filepath}")

            @click.command(cls=NetworkBoundCommand, short_help=f"Run '{relative_filepath}'")
            @network_option()
            def call(network):
                _ = network  # Downstream might use this
                with use_temp_sys_path(filepath.parent.parent):
                    ns = run_module(f"scripts.{filepath.stem}")

                # Nothing to call, everything executes on loading
                self._namespace[filepath.stem] = ns

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

        commands = {}
        for filepath in self._project.scripts_folder.glob("*.py"):
            if filepath.stem.startswith("_"):
                continue  # Ignore any "private" files

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
            # TODO: Figure out how to pull out namespace for `extra_locals`
            return console(
                project=self._project,
                extra_locals=self._namespace[self._command_called],
            )

        return result


@click.command(
    cls=ScriptCommand,
    short_help="Run scripts from the `scripts/` folder",
)
@click.option(
    "-i",
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
