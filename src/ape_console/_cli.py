import faulthandler
import inspect
import logging
import sys
from functools import cached_property
from importlib import import_module
from importlib.machinery import SourceFileLoader
from importlib.util import module_from_spec, spec_from_loader
from os import environ
from pathlib import Path
from types import ModuleType
from typing import TYPE_CHECKING, Any, Optional, Union, cast

import click

from ape.cli.commands import ConnectedProviderCommand
from ape.cli.options import ape_cli_context, project_option

if TYPE_CHECKING:
    from IPython.terminal.ipapp import Config as IPythonConfig

    from ape.managers.project import ProjectManager

CONSOLE_EXTRAS_FILENAME = "ape_console_extras.py"


def _code_callback(ctx, param, value) -> list[str]:
    if not value:
        return value

    # NOTE: newlines are escaped in code automatically, so we
    #   need to de-escape them. Any actually escaped newlines
    #   will still be escaped.
    value = value.replace("\\n", "\n").replace("\\t", "\t").replace("\\b", "\b")

    return value.splitlines()


@click.command(
    cls=ConnectedProviderCommand,
    short_help="Load the console",
    context_settings=dict(ignore_unknown_options=True),
)
@ape_cli_context()
@project_option(hidden=True, type=Path)  # Hidden as mostly used for test purposes.
@click.option("-c", "--code", help="Program passed in as a string", callback=_code_callback)
def cli(cli_ctx, project, code):
    """Opens a console for the local project."""
    verbose = cli_ctx.logger.level == logging.DEBUG
    return console(project=project, verbose=verbose, code=code)


def import_extras_file(file_path) -> ModuleType:
    """Import a module"""
    loader = SourceFileLoader(file_path.name[:-3], str(file_path))
    spec = spec_from_loader(loader.name, loader)

    assert spec is not None

    module = module_from_spec(spec)
    loader.exec_module(module)

    return module


class ApeConsoleNamespace(dict):
    def __init__(self, **kwargs):
        # Initialize the dictionary with provided keyword arguments
        project = kwargs.get("project", self._ape.project)
        kwargs["project"] = self._ape.Project(project) if isinstance(project, Path) else project
        super().__init__(**kwargs)

    def __getitem__(self, key: str):
        # First, attempt to retrieve the key from the dictionary itself
        if super().__contains__(key):
            return super().__getitem__(key)

        # Custom behavior for "ape" key
        if key == "ape":
            res = self._ape
            self[key] = res  # Cache the result
            return res

        # Attempt to get the key from extras
        try:
            res = self._get_extra(key)
        except KeyError:
            pass
        else:
            self[key] = res  # Cache the result
            return res

        # Attempt to retrieve the key from the Ape module.
        try:
            res = self._get_from_ape(key)
        except AttributeError:
            raise KeyError(key)

        # Cache the result and return
        self[key] = res
        return res

    def __setitem__(self, key, value):
        # Override to set items directly into the dictionary
        super().__setitem__(key, value)

    def __contains__(self, item: str) -> bool:  # type: ignore
        return self.get(item) is not None

    def update(self, mapping, **kwargs) -> None:  # type: ignore
        # Override to update the dictionary directly
        super().update(mapping, **kwargs)

    @property
    def _ape(self) -> ModuleType:
        return import_module("ape")

    @cached_property
    def _local_path(self) -> Path:
        return self["project"].path.joinpath(CONSOLE_EXTRAS_FILENAME)

    @cached_property
    def _global_path(self) -> Path:
        return self._ape.config.DATA_FOLDER.joinpath(CONSOLE_EXTRAS_FILENAME)

    @cached_property
    def _local_extras(self) -> dict:
        return self._load_extras_file(self._local_path)

    @cached_property
    def _global_extras(self) -> dict:
        return self._load_extras_file(self._global_path)

    def get(self, key: str, default: Optional[Any] = None):
        try:
            return self.__getitem__(key)
        except KeyError:
            return default

    def _get_extra(self, key: str):
        try:
            return self._local_extras[key]
        except KeyError:
            return self._global_extras[key]

    def _get_from_ape(self, key: str):
        return getattr(self._ape, key)

    def _load_extras_file(self, extras_file: Path) -> dict:
        if not extras_file.is_file():
            return {}

        module = import_extras_file(extras_file)
        ape_init_extras = getattr(module, "ape_init_extras", None)
        all_extras: dict = {}

        if ape_init_extras is not None:
            func_spec = inspect.getfullargspec(ape_init_extras)
            init_kwargs: dict[str, Any] = {k: self._get_from_ape(k) for k in func_spec.args}
            extras = ape_init_extras(**init_kwargs)

            if isinstance(extras, dict):
                all_extras.update(extras)

        all_extras.update({k: getattr(module, k) for k in dir(module) if k not in all_extras})
        return all_extras


def console(
    project: Optional[Union["ProjectManager", Path]] = None,
    verbose: bool = False,
    extra_locals: Optional[dict] = None,
    embed: bool = False,
    code: Optional[list[str]] = None,
):
    import IPython
    from IPython.terminal.ipapp import Config as IPythonConfig

    from ape.utils.misc import _python_version
    from ape.version import version as ape_version

    extra_locals = extra_locals or {}
    if project is None:
        from ape.utils.basemodel import ManagerAccessMixin

        project = ManagerAccessMixin.local_project

    else:
        extra_locals["project"] = project

    project_path: Path = project if isinstance(project, Path) else project.path
    banner = ""
    if verbose:
        banner = """
   Python:  {python_version}
  IPython:  {ipython_version}
      Ape:  {ape_version}
  Project:  {project_path}

    Are you ready to Ape, anon?
    """.format(
            python_version=_python_version,
            ipython_version=IPython.__version__,
            ape_version=ape_version,
            project_path=project_path,
        )

        if not environ.get("APE_TESTING"):
            faulthandler.enable()  # NOTE: In case we segfault

    # Allows modules relative to the project.
    sys.path.insert(0, f"{project_path}")

    ipy_config = IPythonConfig()
    ape_testing = environ.get("APE_TESTING")
    if ape_testing:
        ipy_config.HistoryManager.enabled = False

        # Required for click.testing.CliRunner support.
        embed = True

    namespace = _create_namespace(**extra_locals)
    _launch_console(namespace, ipy_config, embed, banner, code=code)


def _create_namespace(**values) -> dict:
    # Abstracted for testing purposes.
    return ApeConsoleNamespace(**values)


def _launch_console(
    namespace: dict,
    ipy_config: "IPythonConfig",
    embed: bool,
    banner: str,
    code: Optional[list[str]],
):
    import IPython

    from ape_console.config import ConsoleConfig

    ipython_kwargs = {"user_ns": namespace, "config": ipy_config}
    if code:
        _execute_code(code, **ipython_kwargs)
    elif embed:
        IPython.embed(**ipython_kwargs, colors="Neutral", banner1=banner)
    else:
        ipy_config.TerminalInteractiveShell.colors = "Neutral"
        ipy_config.TerminalInteractiveShell.banner1 = banner
        console_config = cast(ConsoleConfig, namespace["ape"].config.get_config("console"))
        ipy_config.InteractiveShellApp.extensions.append("ape_console.plugin")
        if console_config.plugins:
            ipy_config.InteractiveShellApp.extensions.extend(console_config.plugins)

        IPython.start_ipython(**ipython_kwargs, argv=())


def _execute_code(code: list[str], **ipython_kwargs):
    from IPython import InteractiveShell

    shell = InteractiveShell.instance(**ipython_kwargs)
    # NOTE: Using `store_history=True` just so the cell IDs are accurate.
    for line in code:
        shell.run_cell(line, store_history=True)
