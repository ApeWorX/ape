import faulthandler
import logging

import click
import IPython  # type: ignore

from ape.cli import NetworkBoundCommand, ape_cli_context, network_option
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
    return console(cli_ctx.project, verbose=verbose)


def console(project, verbose=None, extra_locals=None):
    import ape

    banner = ""
    if verbose:
        banner = """
   Python:  {python_version}
  IPython:  {ipython_version}
      Ape:  {ape_version}
  Project:  {project_path}

    Are you ready to Ape, anon?
    """.format(
            python_version=ape._python_version,
            ipython_version=IPython.__version__,
            ape_version=ape_version,
            project_path=project.path,
        )

        faulthandler.enable()  # NOTE: In case we segfault

    namespace = {component: getattr(ape, component) for component in ape.__all__}

    if extra_locals:
        namespace.update(extra_locals)

    IPython.embed(colors="Neutral", banner1=banner, user_ns=namespace)
