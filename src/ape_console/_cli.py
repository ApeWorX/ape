import faulthandler

import click
import IPython  # type: ignore

from ape import networks
from ape import project as default_project
from ape.options import network_option, verbose_option
from ape.version import version as ape_version  # type: ignore


@click.command(short_help="Load the console", context_settings=dict(ignore_unknown_options=True))
@verbose_option(help="Display more information in the console")
@network_option
def cli(verbose, network):
    """
    Opens a console for the local project."""

    with networks.parse_network_choice(network):
        return console(verbose=verbose)


def console(project=None, verbose=False, extra_locals=None):
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
