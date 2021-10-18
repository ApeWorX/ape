from typing import Optional, Type

import click

from ape.api import AccountAPI
from ape.cli import AccountAliasPromptChoice
from ape.logging import logger


class Abort(click.ClickException):
    """Wrapper around a CLI exception"""

    def show(self, file=None):
        """Override default ``show`` to print CLI errors in red text."""
        logger.error(self.format_message())


def get_user_selected_account(account_type: Optional[Type[AccountAPI]] = None) -> AccountAPI:
    """
    Prompts the user to pick from their accounts
    and returns that account. Optionally filter the accounts
    by type.
    """
    prompt = AccountAliasPromptChoice(account_type=account_type)
    return prompt.get_user_selected_account()
