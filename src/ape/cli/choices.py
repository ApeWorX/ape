import re
import warnings
from enum import Enum
from functools import lru_cache
from typing import Any, Callable, Iterator, List, Optional, Sequence, Type, Union

import click
from click import BadParameter, Choice, Context, Parameter

from ape.api.accounts import AccountAPI
from ape.api.providers import ProviderAPI
from ape.exceptions import AccountsError
from ape.types import _LazySequence
from ape.utils.basemodel import ManagerAccessMixin

_ACCOUNT_TYPE_FILTER = Union[
    None, Sequence[AccountAPI], Type[AccountAPI], Callable[[AccountAPI], bool]
]


def _get_accounts(key: _ACCOUNT_TYPE_FILTER) -> List[AccountAPI]:
    add_test_accounts = False
    if key is None:
        account_list = list(ManagerAccessMixin.account_manager)

        # Include test accounts at end.
        add_test_accounts = True

    elif isinstance(key, type):
        # Filtering by type.
        account_list = ManagerAccessMixin.account_manager.get_accounts_by_type(key)

    elif isinstance(key, (list, tuple, set)):
        # Given an account list.
        account_list = key  # type: ignore

    else:
        # Filtering by callable.
        account_list = [a for a in ManagerAccessMixin.account_manager if key(a)]  # type: ignore

    sorted_accounts = sorted(account_list, key=lambda a: a.alias or "")
    if add_test_accounts:
        sorted_accounts.extend(ManagerAccessMixin.account_manager.test_accounts)

    return sorted_accounts


class Alias(click.Choice):
    """
    A ``click.Choice`` for loading account aliases for the active project at runtime.

    Provide an ``account_type`` to limit the type of account to choose from.
    Defaults to all account types in ``choices()``.
    """

    name = "alias"

    def __init__(self, key: _ACCOUNT_TYPE_FILTER = None):
        # NOTE: we purposely skip the constructor of `Choice`
        self.case_sensitive = False
        self._key_filter = key
        self.choices = _LazySequence(self._choices_iterator)

    @property
    def _choices_iterator(self) -> Iterator[str]:
        for acct in _get_accounts(key=self._key_filter):
            if acct.alias is None:
                continue

            yield acct.alias


class PromptChoice(click.ParamType):
    """
    A choice option or argument from user selection.

    Usage example::

        def choice_callback(ctx, param, value):
            return param.type.get_user_selected_choice()

        @click.command()
        @click.option(
            "--choice",
            type=PromptChoice(["foo", "bar"]),
            callback=choice_callback,
        )
        def cmd(choice):
            click.echo(f"__expected_{choice}")
    """

    def __init__(self, choices: Sequence[str], name: Optional[str] = None):
        self.choices = choices
        # Since we purposely skip the super() constructor, we need to make
        # sure the class still has a name.
        self.name = name or "option"

    def print_choices(self):
        """
        Echo the choices to the terminal.
        """
        choices = dict(enumerate(self.choices, 0))
        did_print = False
        for idx, choice in choices.items():
            click.echo(f"{idx}. {choice}")
            did_print = True

        if did_print:
            click.echo()

    def convert(
        self, value: Any, param: Optional[Parameter], ctx: Optional[Context]
    ) -> Optional[Any]:
        # noinspection PyBroadException
        try:
            choice_index = int(value)
            if choice_index < 0:
                self.fail("Invalid choice", param=param)

            return self.choices[choice_index]

        except Exception:
            return self.fail_from_invalid_choice(param)

    def fail_from_invalid_choice(self, param):
        return self.fail("Invalid choice.", param=param)

    def select(self) -> str:
        choices = "\n".join(self.choices)
        choice = click.prompt(f"Select one of the following:\n{choices}").strip()
        if not choice.isnumeric():
            return choice

        # User input an index.
        choice_idx = int(choice)
        if 0 <= choice_idx < len(self.choices):
            return self.choices[choice_idx]

        raise IndexError(f"Choice index '{choice_idx}' out of range.")


def get_user_selected_account(
    prompt_message: Optional[str] = None, account_type: _ACCOUNT_TYPE_FILTER = None
) -> AccountAPI:
    """
    **DEPRECATED**: Use :meth:`~ape.cli.choices.select_account` instead.
    """
    warnings.warn(
        "'get_user_selected_account' is deprecated. Use 'select_account'.", DeprecationWarning
    )
    return select_account(prompt_message=prompt_message, key=account_type)


def select_account(
    prompt_message: Optional[str] = None, key: _ACCOUNT_TYPE_FILTER = None
) -> AccountAPI:
    """
    Prompt the user to pick from their accounts and return that account.
    Use this method if you want to prompt users to select accounts _outside_
    of CLI options. For CLI options, use
    :meth:`~ape.cli.options.account_option`.

    Args:
        prompt_message (Optional[str]): Customize the prompt message.
        key (Union[None, Type[AccountAPI], Callable[[AccountAPI], bool]]):
          If given, the user may only select a matching account. You can provide
          a list of accounts, an account class type, or a callable for filtering
          the accounts.

    Returns:
        :class:`~ape.api.accounts.AccountAPI`
    """

    if key and isinstance(key, type) and not issubclass(key, AccountAPI):
        raise AccountsError(f"Cannot return accounts with type '{key}'.")

    prompt = AccountAliasPromptChoice(prompt_message=prompt_message, key=key)
    return prompt.select_account()


class AccountAliasPromptChoice(PromptChoice):
    """
    Prompts the user to select an alias from their accounts.
    Useful for adhoc scripts to lessen the need to hard-code aliases.
    """

    def __init__(
        self,
        key: _ACCOUNT_TYPE_FILTER = None,
        prompt_message: Optional[str] = None,
        name: str = "account",
    ):
        # NOTE: we purposely skip the constructor of `PromptChoice`
        self._key_filter = key
        self._prompt_message = prompt_message or "Select an account"
        self.name = name
        self.choices = _LazySequence(self._choices_iterator)

    def convert(
        self, value: Any, param: Optional[Parameter], ctx: Optional[Context]
    ) -> Optional[AccountAPI]:
        if value is None:
            return None

        if isinstance(value, str) and value.isnumeric():
            alias = super().convert(value, param, ctx)
        else:
            alias = value

        if isinstance(alias, str) and alias.startswith("TEST::"):
            idx_str = value.replace("TEST::", "")
            if not idx_str.isnumeric():
                self.fail(f"Cannot reference test account by '{value}'.", param=param)

            account_idx = int(idx_str)
            if 0 <= account_idx < len(ManagerAccessMixin.account_manager.test_accounts):
                return ManagerAccessMixin.account_manager.test_accounts[int(idx_str)]

            self.fail(f"Index '{idx_str}' is not valid.", param=param)

        elif alias and alias in ManagerAccessMixin.account_manager.aliases:
            return ManagerAccessMixin.account_manager.load(alias)

        return None

    def print_choices(self):
        choices = dict(enumerate(self.choices, 0))
        did_print = False
        for idx, choice in choices.items():
            if not choice.startswith("TEST::"):
                click.echo(f"{idx}. {choice}")
                did_print = True

        len_test_accounts = len(ManagerAccessMixin.account_manager.test_accounts) - 1
        if len_test_accounts > 0:
            msg = "'TEST::account_idx', where `account_idx` is in [0..{len_test_accounts}]\n"
            if did_print:
                msg = f"Or {msg}"

            click.echo(msg)

        elif did_print:
            click.echo()

    @property
    def _choices_iterator(self) -> Iterator[str]:
        # NOTE: Includes test accounts unless filtered out by key.
        for account in _get_accounts(key=self._key_filter):
            if account and (alias := account.alias):
                yield alias

    def select_account(self) -> AccountAPI:
        """
        Returns the selected account.

        Returns:
            :class:`~ape.api.accounts.AccountAPI`
        """

        if not self.choices or len(self.choices) == 0:
            raise AccountsError("No accounts found.")
        elif len(self.choices) == 1 and self.choices[0].startswith("TEST::"):
            return ManagerAccessMixin.account_manager.test_accounts[
                int(self.choices[0].replace("TEST::", ""))
            ]
        elif len(self.choices) == 1:
            return ManagerAccessMixin.account_manager.load(self.choices[0])

        self.print_choices()
        return click.prompt(self._prompt_message, type=self)

    def fail_from_invalid_choice(self, param):
        return self.fail("Invalid choice. Type the number or the alias.", param=param)


_NETWORK_FILTER = Optional[Union[List[str], str]]
_NONE_NETWORK = "__NONE_NETWORK__"


def get_networks(
    ecosystem: _NETWORK_FILTER = None,
    network: _NETWORK_FILTER = None,
    provider: _NETWORK_FILTER = None,
) -> _LazySequence:
    # NOTE: Use str-keys and lru_cache.
    return _get_networks_sequence_from_cache(
        _network_filter_to_key(ecosystem),
        _network_filter_to_key(network),
        _network_filter_to_key(provider),
    )


@lru_cache(maxsize=None)
def _get_networks_sequence_from_cache(ecosystem_key: str, network_key: str, provider_key: str):
    return _LazySequence(
        ManagerAccessMixin.network_manager.get_network_choices(
            ecosystem_filter=_key_to_network_filter(ecosystem_key),
            network_filter=_key_to_network_filter(network_key),
            provider_filter=_key_to_network_filter(provider_key),
        )
    )


def _network_filter_to_key(filter_: _NETWORK_FILTER) -> str:
    if filter_ is None:
        return "__none__"

    elif isinstance(filter_, list):
        return ",".join(filter_)

    return filter_


def _key_to_network_filter(key: str) -> _NETWORK_FILTER:
    if key == "__none__":
        return None

    elif "," in key:
        return [n.strip() for n in key.split(",")]

    return key


class NetworkChoice(click.Choice):
    """
    A ``click.Choice`` to provide network choice defaults for the active project.

    Optionally provide a list of ecosystem names, network names, or provider names
    to filter the results by.

    This is used in :meth:`~ape.cli.options.network_option`.
    """

    CUSTOM_NETWORK_PATTERN = re.compile(r"\w*:\w*:(https?|wss?)://\w*.*|.*\.ipc")

    def __init__(
        self,
        case_sensitive=True,
        ecosystem: _NETWORK_FILTER = None,
        network: _NETWORK_FILTER = None,
        provider: _NETWORK_FILTER = None,
        base_type: Type = ProviderAPI,
        callback: Optional[Callable] = None,
    ):
        if not issubclass(base_type, (ProviderAPI, str)):
            raise TypeError(f"Unhandled type '{base_type}' for NetworkChoice.")

        self.base_type = base_type
        self.callback = callback
        super().__init__(
            get_networks(ecosystem=ecosystem, network=network, provider=provider), case_sensitive
        )

    def get_metavar(self, param):
        return "[ecosystem-name][:[network-name][:[provider-name]]]"

    def convert(self, value: Any, param: Optional[Parameter], ctx: Optional[Context]) -> Any:
        choice: Optional[Union[str, ProviderAPI]]
        if not value:
            choice = None

        elif value.lower() in ("none", "null"):
            choice = _NONE_NETWORK

        elif self.is_custom_value(value):
            # By-pass choice constraints when using custom network.
            choice = value

        else:
            # Regular conditions.
            try:
                # Validate result.
                choice = super().convert(value, param, ctx)
            except BadParameter as err:
                # If an error was not raised for some reason, raise a simpler error.
                # NOTE: Still avoid showing the massive network options list.
                raise click.BadParameter(
                    "Invalid network choice. Use `ape networks list` to see options."
                ) from err

        if (
            choice not in (None, _NONE_NETWORK)
            and isinstance(choice, str)
            and issubclass(self.base_type, ProviderAPI)
        ):
            # Return the provider.

            choice = ManagerAccessMixin.network_manager.get_provider_from_choice(
                network_choice=value
            )

        return self.callback(ctx, param, choice) if self.callback else choice

    @classmethod
    def is_custom_value(cls, value) -> bool:
        return (
            value is not None
            and isinstance(value, str)
            and cls.CUSTOM_NETWORK_PATTERN.match(value) is not None
            or str(value).startswith("http://")
            or str(value).startswith("https://")
        )


class OutputFormat(Enum):
    """
    An enum representing output formats, such as ``TREE`` or ``YAML``.
    Use this to select a subset of common output formats to use
    when creating a :meth:`~ape.cli.choices.output_format_choice`.
    """

    TREE = "TREE"
    """A rich text tree view of the data."""

    YAML = "YAML"
    """A standard .yaml format of the data."""


def output_format_choice(options: Optional[List[OutputFormat]] = None) -> Choice:
    """
    Returns a ``click.Choice()`` type for the given options.

    Args:
        options (List[:class:`~ape.choices.OutputFormat`], optional):
          Limit the formats to accept. Defaults to allowing all formats.

    Returns:
        :class:`click.Choice`
    """

    options = options or list(OutputFormat)

    # Uses `str` form of enum for CLI choices.
    return click.Choice([o.value for o in options], case_sensitive=False)
