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
        self.choice_index = None

    def print_choices(self):
        choices = dict(enumerate(self.choices, 1))
        for choice in choices:
            click.echo(f"{choice}. {choices[choice]}")
        click.echo()

    def convert(
        self, value: Any, param: Optional[Parameter], ctx: Optional[Context]
    ) -> Optional[str]:
        # noinspection PyBroadException
        try:
            self.choice_index = int(value) - 1
            if self.choice_index < 0:
                self.fail("Invalid choice", param=param)

            choice = self.choices[self.choice_index]
            return choice

        except Exception:
            return self.fail("Invalid choice. Type the number of the option above.", param=param)


class AccountAliasPromptChoice(PromptChoice):
    """
    Prompts the user to select an alias from their accounts.
    Useful for adhoc scripts to lessen the need to hard-code aliases.
    """

    def __init__(self, account_type: Optional[Type[AccountAPI]] = None):
        options = [a.alias for a in _get_account_by_type(account_type)]
        super().__init__(options)

    def get_user_selected_account(self) -> AccountAPI:
        """
        Returns the selected account.
        """
        if not self.choices:
            raise AccountsError("There are no accounts.")

        self.print_choices()
        selected_alias = click.prompt("Select an account", type=self)
        return accounts.load(selected_alias)


class NetworkChoice(click.Choice):
    """Wraps ``click.Choice`` to provide network choice defaults for the active project."""

    def __init__(self, case_sensitive=True):
        super().__init__(list(networks.network_choices), case_sensitive)

    def get_metavar(self, param):
        return "[ecosystem-name][:[network-name][:[provider-name]]]"
