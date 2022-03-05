import faulthandler
import io
import logging
from importlib.machinery import SourceFileLoader

import click
import IPython  # type: ignore

from ape import config
from ape import project as default_project
from ape.cli import NetworkBoundCommand, ape_cli_context, network_option
from ape.utils import _python_version
from ape.version import version as ape_version  # type: ignore


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


def load_consolerc(namespace):
    """load and return namespace from consolerc.py if it exists"""
    consolerc = config.DATA_FOLDER.joinpath("consolerc.py")

    if consolerc.is_file():
        module = SourceFileLoader(consolerc.name[:-3], str(consolerc)).load_module()

        # Look for an initrc function
        if hasattr(module, "initrc"):  # and hasattr(module.initrc, "__call__"):
            # Execute functionality with existing console namespace so the
            # script can modify things as it needs
            module.initrc(namespace)

        return {k: getattr(module, k) for k in dir(module) if k != "w" and not k.startswith("_")}


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

    rc_symbols = load_consolerc(namespace)

    if rc_symbols:
        namespace.update(rc_symbols)

    IPython.embed(colors="Neutral", banner1=banner, user_ns=namespace)
