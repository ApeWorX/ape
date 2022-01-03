from typing import List, Optional, Union

import click

from ape import networks, project
from ape.cli.choices import (
    AccountAliasPromptChoice,
    NetworkChoice,
    OutputFormat,
    output_format_choice,
)
from ape.cli.utils import Abort
from ape.exceptions import ContractError
from ape.logging import LogLevel, logger
from ape.managers.project import ProjectManager
from ape.types import ContractType


class ApeCliContextObject:
    """
    A ``click`` context object class. Use via :meth:`~ape.cli.options.ape_cli_context()`.
    It provides common CLI utilities for ape, such as logging or
    access to the managers.
    """

    def __init__(self):
        self.logger = logger
        self._project = None

    @property
    def project(self) -> ProjectManager:
        """
        A class representing the project that is active at runtime.
        (This is the same object as from ``from ape import project``).

        Returns:
            :class:`~ape.managers.project.ProjectManager`
        """

        if not self._project:
            from ape import project

            self._project = project

        return self._project

    @staticmethod
    def abort(msg: str, base_error: Exception = None):
        """
        End execution of the current command invocation.

        Args:
            msg (str): A message to output to the terminal.
            base_error (Exception, optional): Optionally provide
              an error to preserve the exception stack.
        """

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
    """
    A ``click`` context object with helpful utilities.
    Use in your commands to get access to common utility features,
    such as logging or accessing managers.
    """

    def decorator(f):
        f = verbosity_option(logger)(f)
        f = click.make_pass_decorator(ApeCliContextObject, ensure=True)(f)
        return f

    return decorator


def network_option(default: str = None):
    """
    A ``click.option`` for specifying a network.

    Args:
        default (str): Optionally, change which network to
          use as the default. Defaults to how ``ape`` normally
          selects a default network.
    """
    default = default or networks.default_ecosystem.name
    return click.option(
        "--network",
        type=NetworkChoice(case_sensitive=False),
        default=default,
        help="Override the default network and provider. (see ``ape networks list`` for options)",
        show_default=True,
        show_choices=False,
    )


def skip_confirmation_option(help=""):
    """
    A ``click.option`` for skipping confirmation (``--yes``).

    Args:
        help (str): CLI option help text. Defaults to ``""``.
    """

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

    Raises:
        :class:`~ape.exceptions.ContractError`: In the callback when it fails to load the contracts.
    """

    help = help or "The name of a contract in the current project"
    return click.option(
        "--contract", help=help, required=required, callback=_load_contracts, multiple=multiple
    )


def output_format_option(default: OutputFormat = OutputFormat.TREE):
    """
    A ``click.option`` for specifying a format to use when outputting data.

    Args:
        default (:class:`~ape.cli.choices.OutputFormat`): Defaults to ``TREE`` format.
    """

    return click.option(
        "--format",
        "output_format",
        type=output_format_choice(),
        default=default.value,
        callback=lambda ctx, param, value: OutputFormat(value.upper()),
    )
