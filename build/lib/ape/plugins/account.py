from typing import Tuple, Type

from ape.api.accounts import AccountAPI, AccountContainerAPI

from .pluggy_patch import PluginType, hookspec


class AccountPlugin(PluginType):
    """
    An account-related plugin. The plugin must register both
    an :class:`ape.api.accounts.AccountContainerAPI` as well as an
    :class:`ape.api.accounts.AccountAPI`.
    """

    @hookspec
    def account_types(self) -> Tuple[Type[AccountContainerAPI], Type[AccountAPI]]:
        """
        A hook for returning a tuple of an account container and an account type.
        Each account-base plugin defines and returns their own types here.

        Usage example::

            @plugins.register(plugins.AccountPlugin)
            def account_types():
                return AccountContainer, KeyfileAccount


        Returns:
            Tuple[Type[:class:`~ape.api.accounts.AccountContainerAPI`],
            Type[:class:`~ape.api.accounts.AccountAPI`]]
        """
