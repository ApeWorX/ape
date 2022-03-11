from typing import List, Optional, Union

import click
from ethpm_types import ContractType

from ape import networks, project
from ape.cli.choices import (
    AccountAliasPromptChoice,
    NetworkChoice,
    OutputFormat,
    output_format_choice,
)
from ape.cli.utils import Abort
from ape.exceptions import ContractError
from ape.logging import DEFAULT_LOG_LEVEL, LogLevel, logger
from ape.managers.base import ManagerAccessMixin


class ApeCliContextObject(ManagerAccessMixin):
    """
    A ``click`` context object class. Use via :meth:`~ape.cli.options.ape_cli_context()`.
    It provides common CLI utilities for ape, such as logging or
    access to the managers.
    """

    def __init__(self):
        self.logger = logger
        self.config_manager.load()

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
            default=DEFAULT_LOG_LEVEL,
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


def network_option(
    default: Optional[str] = None,
    ecosystem: Optional[Union[List[str], str]] = None,
    network: Optional[Union[List[str], str]] = None,
    provider: Optional[Union[List[str], str]] = None,
):
    """
    A ``click.option`` for specifying a network.

    Args:
        default (Optional[str]): Optionally, change which network to
          use as the default. Defaults to how ``ape`` normally
          selects a default network.
        ecosystem (Optional[Union[List[str], str]]): Filter the options by ecosystem.
          Defaults to getting all ecosystems.
        network (Optional[Union[List[str], str]]): Filter the options by network.
          Defaults to getting all networks in ecosystems.
        provider (Optional[Union[List[str], str]]): Filter the options by provider.
          Defaults to getting all providers in networks.
    """

    if not default:
        if ecosystem:
            default = ecosystem[0] if isinstance(ecosystem, (list, tuple)) else ecosystem
        else:
            default = networks.default_ecosystem.name

    return click.option(
        "--network",
        type=NetworkChoice(
            case_sensitive=False, ecosystem=ecosystem, network=network, provider=provider
        ),
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


def account_option():
    """
    A CLI option that accepts either the account alias or the account number.
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


def incompatible_with(incompatible_opts):
    """
    Factory for creating custom ``click.Option`` subclasses that
    enforce incompatibility with the option strings passed to this function.

    Usage example::

        import click

        @click.command()
        @click.option("--option", cls=incompatible_with(["other_option"]))
        def cmd(option, other_option):
            ....
    """

    if isinstance(incompatible_opts, str):
        incompatible_opts = [incompatible_opts]

    class IncompatibleOption(click.Option):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)

        def handle_parse_result(self, ctx, opts, args):
            # if None it means we're in autocomplete mode and don't want to validate
            if ctx.obj is not None:
                found_incompatible = ", ".join(
                    [f"--{opt.replace('_', '-')}" for opt in opts if opt in incompatible_opts]
                )
                if self.name in opts and found_incompatible:
                    name = self.name.replace("_", "-")
                    raise click.BadOptionUsage(
                        option_name=self.name,
                        message=f"'--{name}' can't be used with '{found_incompatible}'.",
                    )
            return super().handle_parse_result(ctx, opts, args)

    return IncompatibleOption
