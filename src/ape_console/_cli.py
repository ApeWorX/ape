import faulthandler

import click
import IPython  # type: ignore

from ape import networks
from ape import project as default_project
from ape.version import version as ape_version  # type: ignore


class NetworkChoice(click.Choice):
    def __init__(self, case_sensitive=True):
        super().__init__(list(networks.network_choices), case_sensitive)

    def get_metavar(self, param):
        return "ecosystem-name[:network-name[:provider-name]]"


@click.command(short_help="Load the console", context_settings=dict(ignore_unknown_options=True))
@click.option("--verbose", is_flag=True, flag_value=True, default=False)
@click.option(
    "--network",
    type=NetworkChoice(case_sensitive=False),
    default=networks.default_ecosystem.name,
    help="Override the default network and provider. (see `ape networks list` for options)",
    show_default=True,
    show_choices=False,
)
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
