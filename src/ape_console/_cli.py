import click
import IPython  # type: ignore
from IPython.terminal.ipapp import load_default_config  # type: ignore

import ape
from ape.version import version as ape_version


@click.command(short_help="Load the console", context_settings=dict(ignore_unknown_options=True))
@click.argument("ipython_args", nargs=-1, type=click.UNPROCESSED)
def cli(ipython_args):
    """
    Opens a console for the local project."""
    return console(ipython_args=ipython_args)


def console(project=None, extra_locals=None, ipython_args=None):
    if not project:
        # Use default project
        project = ape.project

    config = load_default_config()
    config.TerminalInteractiveShell.banner1 = """
   Python:  {python_version}
  IPython:  {ipython_version}
      Ape:  {ape_version}
  Project:  {project_path}
""".format(
        python_version=ape._python_version,
        ipython_version=IPython.__version__,
        ape_version=ape_version,
        project_path=project._path,
    )

    namespace = {component: getattr(ape, component) for component in ape.__all__}
    if extra_locals:
        namespace.update(extra_locals)

    return IPython.start_ipython(argv=ipython_args, user_ns=namespace, config=config)
