import click
from typing import List

from ape import accounts, networks
from ape.exceptions import AliasAlreadyInUseError


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


class Alias(click.Choice):
    """Wraps ``click.Choice`` to load account aliases for the active project at runtime."""

    name = "alias"

    def __init__(self):
        # NOTE: we purposely skip the constructor of `Choice`
        self.case_sensitive = False

    @property
    def choices(self) -> List[str]:  # type: ignore
        # NOTE: This is a hack to lazy-load the aliases so CLI invocation works properly
        return list(accounts.aliases)


def _require_non_existing_alias(arg):
    if arg in accounts.aliases:
        raise AliasAlreadyInUseError(arg)
    return arg


existing_alias_argument = click.argument("alias", type=Alias())
non_existing_alias_argument = click.argument(
    "alias", callback=lambda ctx, param, arg: _require_non_existing_alias(arg)
)
