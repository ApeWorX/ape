import faulthandler
import inspect
import io
import logging
from importlib.machinery import SourceFileLoader
from importlib.util import module_from_spec, spec_from_loader
from types import ModuleType
from typing import Any, Dict

import click
import IPython  # type: ignore

from ape import config
from ape import project as default_project
from ape.cli import NetworkBoundCommand, ape_cli_context, network_option
from ape.utils import _python_version
from ape.version import version as ape_version  # type: ignore

CONSOLE_EXTRAS_FILENAME = "ape_console_extras.py"


@click.command(
    cls=NetworkBoundCommand,
    short_help="Load the console",
    context_settings=dict(ignore_unknown_options=True),
)
@network_option()
@ape_cli_context()
def cli(cli_ctx, network):
    """Opens a console for the local project."""
    verbose = cli_ctx.logger.level == logging.DEBUG
    return console(verbose=verbose)


def import_extras_file(file_path) -> ModuleType:
    """Import a module"""
    loader = SourceFileLoader(file_path.name[:-3], str(file_path))
    spec = spec_from_loader(loader.name, loader)

    assert spec is not None

    module = module_from_spec(spec)
    loader.exec_module(module)

    return module


def load_console_extras(namespace: Dict[str, Any]) -> Dict[str, Any]:
    """load and return namespace updates from ape_console_extras.py  files if
    they exist"""
    global_extras = config.DATA_FOLDER.joinpath(CONSOLE_EXTRAS_FILENAME)
    project_extras = config.PROJECT_FOLDER.joinpath(CONSOLE_EXTRAS_FILENAME)

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
            init_kwargs: Dict[str, Any] = {k: namespace.get(k) for k in func_spec.args}

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


def console(project=None, verbose=None, extra_locals=None):
    import ape

    if not project:
        # Use default project
        project = default_project

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

        try:
            faulthandler.enable()  # NOTE: In case we segfault
        except io.UnsupportedOperation:
            # Likely running in tests
            pass

    namespace = {component: getattr(ape, component) for component in ape.__all__}

    if extra_locals:
        namespace.update(extra_locals)

    console_extras = load_console_extras(namespace)

    if console_extras:
        namespace.update(console_extras)

    IPython.embed(colors="Neutral", banner1=banner, user_ns=namespace)
