import inspect
import sys
from functools import partial
from typing import Callable, Dict, List, NoReturn, Optional, Sequence, Type, Union

import click
from click import Option
from ethpm_types import ContractType

from ape import networks, project
from ape.api import ProviderAPI
from ape.cli.choices import (
    _ACCOUNT_TYPE_FILTER,
    AccountAliasPromptChoice,
    NetworkChoice,
    OutputFormat,
    output_format_choice,
)
from ape.exceptions import Abort, ProjectError
from ape.logging import DEFAULT_LOG_LEVEL, ApeLogger, LogLevel, logger
from ape.managers.base import ManagerAccessMixin

_VERBOSITY_VALUES = ("--verbosity", "-v")


class ApeCliContextObject(ManagerAccessMixin):
    """
    A ``click`` context object class. Use via :meth:`~ape.cli.options.ape_cli_context()`.
    It provides common CLI utilities for ape, such as logging or
    access to the managers.
    """

    def __init__(self):
        self.logger = logger

    @staticmethod
    def abort(msg: str, base_error: Optional[Exception] = None) -> NoReturn:
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


def verbosity_option(cli_logger: Optional[ApeLogger] = None, default: str = DEFAULT_LOG_LEVEL):
    """A decorator that adds a `--verbosity, -v` option to the decorated
    command.
    """
    _logger = cli_logger or logger
    kwarguments = _create_verbosity_kwargs(_logger=_logger, default=default)
    return lambda f: click.option(*_VERBOSITY_VALUES, **kwarguments)(f)


def _create_verbosity_kwargs(
    _logger: Optional[ApeLogger] = None, default: str = DEFAULT_LOG_LEVEL
) -> Dict:
    cli_logger = _logger or logger

    def set_level(ctx, param, value):
        cli_logger._load_from_sys_argv(default=value.upper())

    level_names = [lvl.name for lvl in LogLevel]
    names_str = f"{', '.join(level_names[:-1])}, or {level_names[-1]}"
    return {
        "callback": set_level,
        "default": default or DEFAULT_LOG_LEVEL,
        "metavar": "LVL",
        "expose_value": False,
        "help": f"One of {names_str}",
        "is_eager": True,
    }


def ape_cli_context(
    default_log_level: str = DEFAULT_LOG_LEVEL, obj_type: Type = ApeCliContextObject
):
    """
    A ``click`` context object with helpful utilities.
    Use in your commands to get access to common utility features,
    such as logging or accessing managers.

    Args:
        default_log_level (str): The log-level value to pass to
          :meth:`~ape.cli.options.verbosity_option`.
        obj_type (Type): The context object type. Defaults to
          :class:`~ape.cli.options.ApeCliContextObject`. Sub-class
          the context to extend its functionality in your CLIs,
          such as if you want to add additional manager classes
          to the context.
    """

    def decorator(f):
        f = verbosity_option(logger, default=default_log_level)(f)
        f = click.make_pass_decorator(obj_type, ensure=True)(f)
        return f

    return decorator


class NetworkOption(Option):
    """
    The class used in `:meth:~ape.cli.options.network_option`.
    """

    # NOTE: Has to be kwargs only to avoid multiple-values for arg error.
    def __init__(self, *args, **kwargs) -> None:
        ecosystem = kwargs.pop("ecosystem", None)
        network = kwargs.pop("network", None)
        provider = kwargs.pop("provider", None)
        default = kwargs.pop("default", "auto")
        base_type = kwargs.pop("base_type", ProviderAPI)

        # NOTE: If using network_option, this part is skipped
        #  because parsing happens earlier to handle advanced usage.
        if "type" not in kwargs:
            kwargs["type"] = NetworkChoice(
                case_sensitive=False,
                ecosystem=ecosystem,
                network=network,
                provider=provider,
                base_type=base_type,
            )
        auto = default == "auto"
        required = kwargs.get("required", False)

        if auto and not required:
            if ecosystem:
                default = ecosystem[0] if isinstance(ecosystem, (list, tuple)) else ecosystem

            else:
                # NOTE: Use a function as the default so it is calculated lazily
                def fn():
                    return networks.default_ecosystem.name

                default = fn

        elif auto:
            default = None

        help_msg = (
            "Override the default network and provider. (see `ape networks list` for options)"
        )
        kwargs = {
            "param_decls": ("--network",),
            "help": help_msg,
            "default": default,
            "required": required,
            **kwargs,
        }
        super().__init__(**kwargs)


def network_option(
    default: Optional[Union[str, Callable]] = "auto",
    ecosystem: Optional[Union[List[str], str]] = None,
    network: Optional[Union[List[str], str]] = None,
    provider: Optional[Union[List[str], str]] = None,
    required: bool = False,
    **kwargs,
):
    """
    A ``click.option`` for specifying a network.

    Args:
        default (Optional[str]): Optionally, change which network to
          use as the default. Defaults to how ``ape`` normally
          selects a default network unless ``required=True``, then defaults to ``None``.
        ecosystem (Optional[Union[List[str], str]]): Filter the options by ecosystem.
          Defaults to getting all ecosystems.
        network (Optional[Union[List[str], str]]): Filter the options by network.
          Defaults to getting all networks in ecosystems.
        provider (Optional[Union[List[str], str]]): Filter the options by provider.
          Defaults to getting all providers in networks.
        required (bool): Whether the option is required. Defaults to ``False``.
          When set to ``True``, the default value is ``None``.
        kwargs: Additional overrides to ``click.option``.
    """

    def decorator(f):
        # When using network_option, handle parsing now so we can pass to
        # callback outside of command context.
        kwargs["type"] = kwargs.pop("type", None) or NetworkChoice(
            case_sensitive=False, ecosystem=ecosystem, network=network, provider=provider
        )

        # Find passed --network value
        network_choice = None
        arguments = _get_sys_argv()
        for idx, val in enumerate(arguments):
            if val == "--network":
                next_idx = idx + 1
                if next_idx < len(arguments):
                    network_choice = arguments[next_idx]
                    break

        if network_choice in ("None", "none"):
            # Specified None in cmd line- ignore.
            # Or is an adhoc value.
            choice_classes = None

        elif network_choice is None:
            # Unspecified.
            ecosystem_obj = networks.default_ecosystem
            network_obj = ecosystem_obj.default_network
            choice_classes = {
                "ecosystem": networks.default_ecosystem,
                "network": ecosystem_obj.default_network,
                "provider": network_obj.default_provider,
            }

        else:
            network_ctx = networks.parse_network_choice(network_choice)
            provider_obj = network_ctx._provider
            network_obj = provider_obj.network
            ecosystem_obj = network_obj.ecosystem
            choice_classes = {
                "ecosystem": ecosystem_obj,
                "network": network_obj,
                "provider": provider_obj,
            }

        # Create the callback using values from the parsed network choice.
        # Only pass in values requested. Exposure is optional!
        if choice_classes is None:
            # Was told to use None explicitly.
            partial_f = f

        else:
            partial_kwargs = {}
            signature = inspect.signature(f)
            requested_data = [x.name for x in signature.parameters.values()]
            for arg_type in ("ecosystem", "network", "provider"):
                if arg_type in requested_data:
                    partial_kwargs[arg_type] = choice_classes[arg_type]

            partial_f = partial(f, **partial_kwargs)
            partial_f.__name__ = f.__name__  # type: ignore[attr-defined]

            # Skip NetworkChoice parsing since we did it already here.
            kwargs["type"] = None

            # Set this to false to avoid click passing in a str value for network.
            # This happens with `kwargs["type"] = None` and we are already handling
            # `network` via the partial.
            kwargs["expose_value"] = False

        # Create the actual option.
        option = click.option(
            default=default,
            ecosystem=ecosystem,
            network=network,
            provider=provider,
            required=required,
            cls=NetworkOption,
            **kwargs,
        )(partial_f)

        return option

    return decorator


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
        return param.type.select_account()

    return value


def account_option(account_type: _ACCOUNT_TYPE_FILTER = None):
    """
    A CLI option that accepts either the account alias or the account number.
    If not given anything, it will prompt the user to select an account.
    """

    return click.option(
        "--account",
        type=AccountAliasPromptChoice(key=account_type),
        callback=_account_callback,
    )


def _load_contracts(ctx, param, value) -> Optional[Union[ContractType, List[ContractType]]]:
    if not value:
        return None

    if len(project.contracts) == 0:
        raise ProjectError("Project has no contracts.")

    # If the user passed in `multiple=True`, then `value` is a list,
    # and therefore we should also return a list.
    is_multiple = isinstance(value, (tuple, list))

    def get_contract(contract_name: str) -> ContractType:
        if contract_name not in project.contracts:
            raise ProjectError(f"No contract named '{value}'")

        return project.contracts[contract_name]

    return [get_contract(c) for c in value] if is_multiple else get_contract(value)


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
                if self.name is not None and self.name in opts and found_incompatible:
                    name = self.name.replace("_", "-")
                    raise click.BadOptionUsage(
                        option_name=self.name,
                        message=f"'--{name}' can't be used with '{found_incompatible}'.",
                    )
            return super().handle_parse_result(ctx, opts, args)

    return IncompatibleOption


def _get_sys_argv() -> Sequence[str]:
    # Is separate fn so can be mocked in tests.
    return sys.argv
