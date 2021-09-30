from typing import Any, List, Optional, Type

import click
from click import Context, Parameter

from ape import accounts
from ape.api.accounts import AccountAPI


class Alias(click.Choice):
    """Wraps ``click.Choice`` to load account aliases for the active project at runtime.

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
        options = (
            list(accounts)
            if not self._account_type
            else accounts.get_accounts_by_type(self._account_type)
        )
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
            self.fail("Invalid choice", param=param)
