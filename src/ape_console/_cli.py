import faulthandler
import inspect
import logging
import sys
from importlib.machinery import SourceFileLoader
from importlib.util import module_from_spec, spec_from_loader
from os import environ
from types import ModuleType
from typing import TYPE_CHECKING, Any, Optional, cast

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
@project_option(hidden=True)  # Hidden as mostly used for test purposes.
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


def load_console_extras(**namespace: Any) -> dict[str, Any]:
    """load and return namespace updates from ape_console_extras.py  files if
    they exist"""
    from ape.utils.basemodel import ManagerAccessMixin as access

    pm = namespace.get("project", access.local_project)
    global_extras = pm.config_manager.DATA_FOLDER.joinpath(CONSOLE_EXTRAS_FILENAME)
    project_extras = pm.path.joinpath(CONSOLE_EXTRAS_FILENAME)

    for extras_file in [global_extras, project_extras]:
        if not extras_file.is_file():
            continue

        module = import_extras_file(extras_file)
        ape_init_extras = getattr(module, "ape_init_extras", None)

        # If found, execute ape_init_extras() function.
        if ape_init_extras is not None:
            # Figure out the kwargs the func is looking for and assemble
            # from the original namespace
            func_spec = inspect.getfullargspec(ape_init_extras)
            init_kwargs: dict[str, Any] = {k: namespace.get(k) for k in func_spec.args}

            # Execute functionality with existing console namespace as
            # kwargs.
            extras = ape_init_extras(**init_kwargs)

            # If ape_init_extras returned a dict expect it to be new symbols
            if isinstance(extras, dict):
                namespace.update(extras)

        # Add any public symbols from the module into the console namespace
        for k in dir(module):
            if k != "ape_init_extras" and not k.startswith("_"):
                # Prevent override of existing namespace symbols
                if k in namespace:
                    continue

                namespace[k] = getattr(module, k)

    return namespace


def console(
    project: Optional["ProjectManager"] = None,
    verbose: bool = False,
    extra_locals: Optional[dict] = None,
    embed: bool = False,
    code: Optional[list[str]] = None,
):
    import IPython
    from IPython.terminal.ipapp import Config as IPythonConfig

    import ape
    from ape.utils.misc import _python_version
    from ape.version import version as ape_version

    project = project or ape.project
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
            project_path=project.path,
        )

        if not environ.get("APE_TESTING"):
            faulthandler.enable()  # NOTE: In case we segfault

    namespace = {component: getattr(ape, component) for component in ape.__all__}
    namespace["project"] = project  # Use the given project.
    namespace["ape"] = ape

    # Allows modules relative to the project.
    sys.path.insert(0, f"{project.path}")

    # NOTE: `ape_console_extras` only is meant to work with default namespace.
    #  Load extras before local namespace to avoid console extras receiving
    #  the wrong values for its arguments.
    console_extras = load_console_extras(**namespace)

    if extra_locals:
        namespace.update(extra_locals)

    if console_extras:
        namespace.update(console_extras)

    ipy_config = IPythonConfig()
    ape_testing = environ.get("APE_TESTING")
    if ape_testing:
        ipy_config.HistoryManager.enabled = False

        # Required for click.testing.CliRunner support.
        embed = True

    _launch_console(namespace, ipy_config, embed, banner, code=code)


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
