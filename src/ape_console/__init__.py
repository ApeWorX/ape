import click
import IPython  # type: ignore
from IPython.terminal.ipapp import load_default_config  # type: ignore

import ape
from ape.version import version as ape_version  # type: ignore


@click.command(short_help="Load the console", context_settings=dict(ignore_unknown_options=True))
@click.option("--verbose", is_flag=True, flag_value=True, default=False)
@click.argument("ipython_args", nargs=-1, type=click.UNPROCESSED)
def cli(verbose, ipython_args):
    """
    Opens a console for the local project."""
    return console(verbose=verbose, ipython_args=ipython_args)


def console(project=None, verbose=False, extra_locals=None, ipython_args=None):
    if not project:
        # Use default project
        project = ape.project

    config = load_default_config()

    if verbose:
        config.TerminalInteractiveShell.banner1 = """
   Python:  {python_version}
  IPython:  {ipython_version}
      Ape:  {ape_version}
  Project:  {project_path}
    """.format(
            python_version=ape._python_version,
            ipython_version=IPython.__version__,
            ape_version=ape_version,
            project_path=project.path,
        )

    else:
        config.TerminalInteractiveShell.banner1 = ""

    namespace = {component: getattr(ape, component) for component in ape.__all__}
    if extra_locals:
        namespace.update(extra_locals)

    return IPython.start_ipython(argv=ipython_args, user_ns=namespace, config=config)
