import click
import click_logging  # type: ignore

from ape import networks
from ape.logging import logger as logger
from ape.utils import Abort


class PluginHelper:
    """A class that can be auto-imported into a plugin ``click.command()``
    via ``@plugin_helper()``. It can help do common CLI tasks such as log
    messages to the user or abort execution."""

    _logger = logger

    def log_info(self, msg: str):
        self._logger.info(msg)

    def log_warning(self, msg: str):
        self._logger.warning(msg)

    def log_success(self, msg: str):
        self._logger.success(msg)  # type: ignore

    @staticmethod
    def abort(msg: str, base_error: Exception = None):
        if base_error:
            raise Abort(msg) from base_error
        raise Abort(msg)


def plugin_helper():
    def decorator(f):
        f = click_logging.simple_verbosity_option(
            logger, help="Either CRITICAL, ERROR, WARNING, INFO or DEBUG"
        )(f)
        f = click.make_pass_decorator(PluginHelper, ensure=True)(f)
        return f

    return decorator


class NetworkChoice(click.Choice):
    """Wraps ``click.Choice`` to provide network choice defaults for the active project."""

    def __init__(self, case_sensitive=True):
        super().__init__(list(networks.network_choices), case_sensitive)

    def get_metavar(self, param):
        return "[ecosystem-name][:[network-name][:[provider-name]]]"


network_option = click.option(
    "--network",
    type=NetworkChoice(case_sensitive=False),
    default=networks.default_ecosystem.name,
    help="Override the default network and provider. (see ``ape networks list`` for options)",
    show_default=True,
    show_choices=False,
)


def verbose_option(help=""):
    return click.option(
        "-v",
        "--verbose",
        is_flag=True,
        default=False,
        help=help,
    )
