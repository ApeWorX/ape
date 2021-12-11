from enum import Enum
from typing import Any, List, Optional, Type

import click
from click import Choice, Context, Parameter

from ape import accounts, networks
from ape.api.accounts import AccountAPI
from ape.exceptions import AccountsError


def _get_account_by_type(account_type: Optional[Type[AccountAPI]] = None) -> List[AccountAPI]:
    return list(accounts) if not account_type else accounts.get_accounts_by_type(account_type)


class Alias(click.Choice):
    """
    A ``click.Choice`` for loading account aliases for the active project at runtime.

    Provide an ``account_type`` to limit the type of account to choose from.
    Defaults to all account types in ``choices()``.
    """

    name = "alias"

    # noinspection PyMissingConstructor
    def __init__(self, account_type: Optional[Type[AccountAPI]] = None):
        # NOTE: we purposely skip the constructor of `Choice`
        self.case_sensitive = False
        self._account_type = account_type

    @property
    def choices(self) -> List[str]:  # type: ignore
        """
        The aliases available to choose from.

        Returns:
            list[str]: A list of account aliases the user may choose from.
        """

        options = _get_account_by_type(self._account_type)
        return [a.alias for a in options if a.alias is not None]


class PromptChoice(click.ParamType):
    """
    A choice option or argument from user selection.
    """

    def __init__(self, choices):
        self.choices = choices

    def print_choices(self):
        """
        Echo the choices to the terminal.
        """

        choices = dict(enumerate(self.choices, 0))
        for choice in choices:
            click.echo(f"{choice}. {choices[choice]}")
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


def get_user_selected_account(
    account_type: Optional[Type[AccountAPI]] = None, prompt_message: Optional[str] = None
) -> AccountAPI:
    """
    Prompt the user to pick from their accounts and return that account.
    Use this method if you want to prompt users to select accounts _outside_
    of CLI options. For CLI options, use
    :meth:`~ape.cli.options.account_option_that_prompts_when_not_given`.

    Args:
        account_type (type[:class:`~ape.api.accounts.AccountAPI`], optional):
          If given, the user may only select an account of this type.
        prompt_message (str, optional): Customize the prompt message.

    Returns:
        :class:`~ape.api.accounts.AccountAPI`
    """

    if account_type and (type(account_type) != type or not issubclass(account_type, AccountAPI)):
        raise AccountsError(f"Cannot return accounts with type '{account_type}'.")

    prompt = AccountAliasPromptChoice(account_type=account_type, prompt_message=prompt_message)
    return prompt.get_user_selected_account()


class AccountAliasPromptChoice(PromptChoice):
    """
    Prompts the user to select an alias from their accounts.
    Useful for adhoc scripts to lessen the need to hard-code aliases.
    """

    # noinspection PyMissingConstructor
    def __init__(self, account_type: Optional[Type[AccountAPI]] = None, prompt_message: str = None):
        # NOTE: we purposely skip the constructor of `PromptChoice`
        self._account_type = account_type
        self._prompt_message = prompt_message or "Select an account"

    # type: ignore
    def convert(
        self, value: Any, param: Optional[Parameter], ctx: Optional[Context]
    ) -> Optional[AccountAPI]:
        if value and value in accounts.aliases:
            return accounts.load(value)

        # Prompt the user if they didn't provide a value.
        alias = super().convert(value, param, ctx)
        return accounts.load(alias) if alias else None

    @property
    def choices(self) -> List[str]:
        """
        All the account aliases.

        Returns:
            list[str]: A list of all the account aliases.
        """

        return [
            a.alias
            for a in _get_account_by_type(self._account_type)
            if a is not None and a.alias is not None
        ]

    def get_user_selected_account(self) -> AccountAPI:
        """
        Returns the selected account.
        """

        if not self.choices:
            raise AccountsError("No accounts found.")
        elif len(self.choices) == 1:
            return accounts.load(self.choices[0])

        self.print_choices()
        return click.prompt(self._prompt_message, type=self)

    def fail_from_invalid_choice(self, param):
        return self.fail("Invalid choice. Type the number or the alias.", param=param)


class NetworkChoice(click.Choice):
    """
    A ``click.Choice`` to provide network choice defaults for the active project.
    """

    def __init__(self, case_sensitive=True):
        super().__init__(list(networks.network_choices), case_sensitive)

    def get_metavar(self, param):
        return "[ecosystem-name][:[network-name][:[provider-name]]]"


class OutputFormat(Enum):
    """
    An enum representing output formats, such as ``TREE`` or ``YAML``.
    Use this to select a subset of common output formats to use
    when creating a :meth:`~ape.cli.choices.output_format_choice`.
    """

    TREE = "TREE"
    YAML = "YAML"


def output_format_choice(options: List[OutputFormat] = None) -> Choice:
    """
    Returns a ``click.Choice()`` type for the given options.

    Args:
        options (list[:class:`~ape.choices.OutputFormat`], optional):
          Limit the formats to accept. Defaults to allowing all formats.

    Returns:
        :class:`click.Choice`
    """

    options = options or [o for o in OutputFormat]

    # Uses `str` form of enum for CLI choices.
    return click.Choice([o.value for o in options], case_sensitive=False)
