import re
from enum import Enum
from typing import Any, List, Optional, Type, Union

import click
from click import Choice, Context, Parameter

from ape import accounts, networks
from ape.api.accounts import AccountAPI
from ape.exceptions import AccountsError

ADHOC_NETWORK_PATTERN = re.compile(r"\w*:\w*:https?://\w*.*")


def _get_account_by_type(account_type: Optional[Type[AccountAPI]] = None) -> List[AccountAPI]:
    account_list = (
        list(accounts) if not account_type else accounts.get_accounts_by_type(account_type)
    )
    account_list.sort(key=lambda a: a.alias or "")
    return account_list


class Alias(click.Choice):
    """
    A ``click.Choice`` for loading account aliases for the active project at runtime.

    Provide an ``account_type`` to limit the type of account to choose from.
    Defaults to all account types in ``choices()``.
    """

    name = "alias"

    def __init__(self, account_type: Optional[Type[AccountAPI]] = None):
        # NOTE: we purposely skip the constructor of `Choice`
        self.case_sensitive = False
        self._account_type = account_type

    @property
    def choices(self) -> List[str]:  # type: ignore
        """
        The aliases available to choose from.

        Returns:
            List[str]: A list of account aliases the user may choose from.
        """

        options = _get_account_by_type(self._account_type)
        return [a.alias for a in options if a.alias is not None]


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

    def __init__(self, choices, name: Optional[str] = None):
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

    def get_user_selected_choice(self) -> str:
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
    prompt_message: Optional[str] = None,
    account_type: Optional[Type[AccountAPI]] = None,
) -> AccountAPI:
    """
    Prompt the user to pick from their accounts and return that account.
    Use this method if you want to prompt users to select accounts _outside_
    of CLI options. For CLI options, use
    :meth:`~ape.cli.options.account_option`.

    Args:
        prompt_message (Optional[str]): Customize the prompt message.
        account_type (Optional[Type[:class:`~ape.api.accounts.AccountAPI`]]]):
          If given, the user may only select an account of this type.

    Returns:
        :class:`~ape.api.accounts.AccountAPI`
    """

    if account_type and not issubclass(account_type, AccountAPI):
        raise AccountsError(f"Cannot return accounts with type '{account_type}'.")

    prompt = AccountAliasPromptChoice(prompt_message=prompt_message, account_type=account_type)
    return prompt.get_user_selected_account()


class AccountAliasPromptChoice(PromptChoice):
    """
    Prompts the user to select an alias from their accounts.
    Useful for adhoc scripts to lessen the need to hard-code aliases.
    """

    def __init__(
        self,
        account_type: Optional[Type[AccountAPI]] = None,
        prompt_message: Optional[str] = None,
        name: str = "account",
    ):
        # NOTE: we purposely skip the constructor of `PromptChoice`
        self._account_type = account_type
        self._prompt_message = prompt_message or "Select an account"
        self.name = name

    def convert(
        self, value: Any, param: Optional[Parameter], ctx: Optional[Context]
    ) -> Optional[AccountAPI]:
        if isinstance(value, str) and value.startswith("TEST::"):
            idx_str = value.replace("TEST::", "")
            if not idx_str.isnumeric():
                self.fail(f"Cannot reference test account by '{value}'.", param=param)

            account_idx = int(idx_str)
            if 0 <= account_idx < len(accounts.test_accounts):
                return accounts.test_accounts[int(idx_str)]

            self.fail(f"Index '{idx_str}' is not valid.", param=param)

        if value and value in accounts.aliases:
            return accounts.load(value)

        # Prompt the user if they didn't provide a value.
        alias = super().convert(value, param, ctx)
        return accounts.load(alias) if alias else None

    def print_choices(self):
        choices = dict(enumerate(self.choices, 0))
        did_print = False
        for idx, choice in choices.items():
            if not choice.startswith("TEST::"):
                click.echo(f"{idx}. {choice}")
                did_print = True

        len_test_accounts = len(accounts.test_accounts) - 1
        if len_test_accounts > 0:
            msg = "'TEST::account_idx', where `account_idx` is in [0..{len_test_accounts}]\n"
            if did_print:
                msg = f"Or {msg}"

            click.echo(msg)

        elif did_print:
            click.echo()

    @property
    def choices(self) -> List[str]:
        """
        All the account aliases.

        Returns:
            List[str]: A list of all the account aliases.
        """

        _accounts = [
            a.alias
            for a in _get_account_by_type(self._account_type)
            if a is not None and a.alias is not None
        ]
        _accounts.extend([f"TEST::{i}" for i, _ in enumerate(accounts.test_accounts)])
        return _accounts

    def get_user_selected_account(self) -> AccountAPI:
        """
        Returns the selected account.

        Returns:
            :class:`~ape.api.accounts.AccountAPI`
        """

        if not self.choices:
            raise AccountsError("No accounts found.")
        elif len(self.choices) == 1 and self.choices[0].startswith("TEST::"):
            return accounts.test_accounts[int(self.choices[0].replace("TEST::", ""))]
        elif len(self.choices) == 1:
            return accounts.load(self.choices[0])

        self.print_choices()
        return click.prompt(self._prompt_message, type=self)

    def fail_from_invalid_choice(self, param):
        return self.fail("Invalid choice. Type the number or the alias.", param=param)


class NetworkChoice(click.Choice):
    """
    A ``click.Choice`` to provide network choice defaults for the active project.

    Optionally provide a list of ecosystem names, network names, or provider names
    to filter the results by.

    This is used in :meth:`~ape.cli.options.network_option`.
    """

    def __init__(
        self,
        case_sensitive=True,
        ecosystem: Optional[Union[List[str], str]] = None,
        network: Optional[Union[List[str], str]] = None,
        provider: Optional[Union[List[str], str]] = None,
    ):
        super().__init__(
            list(
                networks.get_network_choices(
                    ecosystem_filter=ecosystem, network_filter=network, provider_filter=provider
                )
            ),
            case_sensitive,
        )

    def get_metavar(self, param):
        return "[ecosystem-name][:[network-name][:[provider-name]]]"

    def convert(self, value: Any, param: Optional[Parameter], ctx: Optional[Context]) -> Any:
        if (
            ADHOC_NETWORK_PATTERN.match(value)
            or str(value).startswith("http://")
            or str(value).startswith("https://")
        ):
            # By-pass choice constraints when using adhoc network
            return value

        return super().convert(value, param, ctx)


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

    options = options or [o for o in OutputFormat]

    # Uses `str` form of enum for CLI choices.
    return click.Choice([o.value for o in options], case_sensitive=False)
