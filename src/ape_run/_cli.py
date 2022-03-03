from importlib.machinery import SourceFileLoader
from pathlib import Path
from types import ModuleType
from typing import Dict, Optional, Union

import click

from ape.logging import logger
from ape.managers.project import ProjectManager
from ape.utils import cached_property, get_relative_path
from ape_console._cli import console


def deepcopy_skip_modules(d):
    return {
        k: deepcopy_skip_modules(v) if isinstance(v, dict) else v
        for k, v in d.items()
        if not k.startswith("_") and not isinstance(v, ModuleType)
    }


class ScriptCommand(click.MultiCommand):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs, result_callback=self.result_callback)

    def __load_module(self, filepath: Path) -> Optional[ModuleType]:
        try:
            # TODO: Analyze security issues from this
            return SourceFileLoader("script", str(filepath)).load_module()

        except Exception as err:
            relative_filepath = get_relative_path(filepath, self._project.path)
            logger.error_from_exception(err, f"Exception while loading script: {relative_filepath}")
            return None

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

            script = self.__load_module(filepath)
            if script:
                return script.cli  # type: ignore

            return None  # NOTE: Allow other scripts to load if loading script breaks

        elif "main" in code.co_names:
            logger.debug(f"Found 'main' method in script: {relative_filepath}")

            @click.command(short_help=f"Run '{relative_filepath}:main'")
            def call():
                module = self.__load_module(filepath)
                if module:
                    module.main()  # type: ignore

            return call

        else:
            logger.warning(f"No 'main' method or 'cli' command in script: {relative_filepath}")

            @click.command(short_help=f"Run '{relative_filepath}'")
            def call():
                self.__load_module(filepath)
                # Nothing to call

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

        project.config.load()

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
            self.command_called = name
            return self.commands[name]

        # NOTE: don't return anything so Click displays proper error

    def result_callback(self, result, interactive):
        if interactive:
            # TODO: Figure out how to pull out namespace for `extra_locals`
            return console(project=self._project, extra_locals={})

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
    Run scripts from the ``scripts`` folder. A script must either define a ``main()`` method,
    or define an import named ``cli`` that is a ``click.Command`` or ``click.Group`` object.
    ``click.Group`` and ``click.Command`` objects will be provided with additional context, which
    will be injected dynamically during script execution. The dynamically injected objects are
    the exports from the ``ape`` top-level package (similar to how the console works)
    """
    _ = interactive  # NOTE: Used in above callback handler
