from typing import Optional, Type

import click

from ape import accounts, networks
from ape.api.accounts import AccountAPI
from ape.cli.choices import Alias
from ape.cli.utils import Abort
from ape.exceptions import AliasAlreadyInUseError
from ape.logging import LogLevel, logger


class ApeCliContextObject:
    """A class that can be auto-imported into a plugin ``click.command()``
    via ``@ape_cli_context()``. It can help do common CLI tasks such as log
    messages to the user or abort execution."""

    def __init__(self):
        self.logger = logger

    @staticmethod
    def abort(msg: str, base_error: Exception = None):
        if base_error:
            logger.error(msg)
            raise Abort(msg) from base_error
        raise Abort(msg)


def verbosity_option(cli_logger):
    """A decorator that adds a `--verbosity, -v` option to the decorated
    command.
    """

    level_names = [lvl.name for lvl in LogLevel]
    names_str = f"{', '.join(level_names[:-1])}, or {level_names[-1]}"

    def decorator(f):
        def _set_level(ctx, param, value):
            log_level = getattr(LogLevel, value.upper(), None)
            if log_level is None:
                raise click.BadParameter(f"Must be one of {names_str}, not {value}")

            cli_logger.setLevel(log_level.name)

        return click.option(
            "--verbosity",
            "-v",
            callback=_set_level,
            default=LogLevel.INFO.name,
            metavar="LVL",
            expose_value=False,
            help=f"One of {names_str}",
            is_eager=True,
        )(f)

    return decorator


def ape_cli_context():
    def decorator(f):
        f = verbosity_option(logger)(f)
        f = click.make_pass_decorator(ApeCliContextObject, ensure=True)(f)
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


def _require_non_existing_alias(arg):
    if arg in accounts.aliases:
        raise AliasAlreadyInUseError(arg)
    return arg


def existing_alias_argument(account_type: Optional[Type[AccountAPI]] = None):
    return click.argument("alias", type=Alias(account_type=account_type))


non_existing_alias_argument = click.argument(
    "alias", callback=lambda ctx, param, arg: _require_non_existing_alias(arg)
)


def skip_confirmation_option(help=""):
    return click.option(
        "-y",
        "--yes",
        "skip_confirmation",
        default=False,
        is_flag=True,
        help=help,
    )
