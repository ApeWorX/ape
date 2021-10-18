from typing import Any, List, Optional, Type

import click
from click import Context, Parameter

from ape import accounts, networks
from ape.api.accounts import AccountAPI
from ape.exceptions import AccountsError


def _get_account_by_type(account_type: Optional[Type[AccountAPI]] = None) -> List[AccountAPI]:
    return list(accounts) if not account_type else accounts.get_accounts_by_type(account_type)


class Alias(click.Choice):
    """Wraps ``click.Choice`` to load account aliases for the active project at runtime.

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
        options = _get_account_by_type(self._account_type)
        return [a.alias for a in options if a.alias is not None]


class PromptChoice(click.ParamType):
    """
    A choice option or argument from user selection.
    """

    def __init__(self, choices):
        self.choices = choices

    def print_choices(self):
        choices = dict(enumerate(self.choices, 1))
        for choice in choices:
            click.echo(f"{choice}. {choices[choice]}")
        click.echo()

    def convert(
        self, value: Any, param: Optional[Parameter], ctx: Optional[Context]
    ) -> Optional[Any]:
        # noinspection PyBroadException
        try:
            choice_index = int(value) - 1
            if choice_index < 0:
                self.fail("Invalid choice", param=param)

            return self.choices[choice_index]

        except Exception:
            return self.fail_from_invalid_choice(param)

    def fail_from_invalid_choice(self, param):
        return self.fail("Invalid choice.", param=param)


class AccountAliasPromptChoice(PromptChoice):
    """
    Prompts the user to select an alias from their accounts.
    Useful for adhoc scripts to lessen the need to hard-code aliases.
    """

    # noinspection PyMissingConstructor
    def __init__(self, account_type: Optional[Type[AccountAPI]] = None):
        # NOTE: we purposely skip the constructor of `PromptChoice`
        self._account_type = account_type

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
        return click.prompt("Select an account", type=self)

    def fail_from_invalid_choice(self, param):
        return self.fail("Invalid choice. Type the number or the alias.", param=param)


class NetworkChoice(click.Choice):
    """Wraps ``click.Choice`` to provide network choice defaults for the active project."""

    def __init__(self, case_sensitive=True):
        super().__init__(list(networks.network_choices), case_sensitive)

    def get_metavar(self, param):
        return "[ecosystem-name][:[network-name][:[provider-name]]]"
