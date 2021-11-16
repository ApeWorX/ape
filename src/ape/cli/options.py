from typing import List, Optional, Union

import click

from ape import networks, project
from ape.cli.choices import AccountAliasPromptChoice, NetworkChoice
from ape.cli.utils import Abort
from ape.exceptions import ContractError
from ape.logging import LogLevel, logger
from ape.types import ContractType


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
                raise click.BadParameter(f"Must be one of {names_str}, not {value}.")

            cli_logger.set_level(log_level.name)

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


def network_option():
    return click.option(
        "--network",
        type=NetworkChoice(case_sensitive=False),
        default=networks.default_ecosystem.name,
        help="Override the default network and provider. (see ``ape networks list`` for options)",
        show_default=True,
        show_choices=False,
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


def _account_callback(ctx, param, value):
    if param and not value:
        return param.type.get_user_selected_account()
    return value


def account_option_that_prompts_when_not_given():
    """
    Accepts either the account alias or the account number.
    If not given anything, it will prompt the user to select an account.
    """
    return click.option(
        "--account",
        type=AccountAliasPromptChoice(),
        callback=_account_callback,
    )


def _load_contracts(ctx, param, value) -> Optional[Union[ContractType, List[ContractType]]]:
    if not value:
        return None

    if len(project.contracts) == 0:
        raise ContractError("Project has no contracts.")

    # If the user passed in `multiple=True`, then `value` is a list,
    # and therefore we should also return a list.
    is_multiple = isinstance(value, (tuple, list))

    def create_contract(contract_name: str) -> ContractType:
        if contract_name not in project.contracts:
            raise ContractError(f"No contract named '{value}'")

        return project.contracts[contract_name]

    return [create_contract(c) for c in value] if is_multiple else create_contract(value)


def contract_option(help=None, required=False, multiple=False):
    """
    Contract(s) from the current project.
    If you pass ``multiple=True``, you will get a list of contract types from the callback.
    """
    help = help or "The name of a contract in the current project"
    return click.option(
        "--contract", help=help, required=required, callback=_load_contracts, multiple=multiple
    )
