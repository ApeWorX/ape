import faulthandler
import io
import logging

import click
import IPython  # type: ignore

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

    IPython.embed(colors="Neutral", banner1=banner, user_ns=namespace)
