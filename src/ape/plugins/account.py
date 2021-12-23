from typing import Tuple, Type

from ape.api.accounts import AccountAPI, AccountContainerAPI

from .pluggy_patch import PluginType, hookspec


class AccountPlugin(PluginType):
    """
    An account-related plugin. The plugin must register both
    a :class:`ape.api.accounts.AccountContainerAPI` as well as a
    :class:`ape.api.accounts.AccountAPI`.
    """

    @hookspec
    def account_types(self) -> Tuple[Type[AccountContainerAPI], Type[AccountAPI]]:
        """
        A hook for returning a tuple of an Account Container and an Account type.
        Each account-base plugin defines and returns their own types here.

        Returns:
            tuple[type[:class:`~ape.api.accounts.AccountContainerAPI`],
            type[:class:`~ape.api.accounts.AccountAPI`]]
        """
