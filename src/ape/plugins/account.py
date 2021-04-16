from typing import Tuple, Type

from ape.api.accounts import AccountAPI, AccountContainerAPI

from .pluggy_patch import PluginType, hookspec


class AccountPlugin(PluginType):
    @hookspec
    def account_types(self) -> Tuple[Type[AccountContainerAPI], Type[AccountAPI]]:
        """
        Must return a tuple of an Account Container and Account type
        """
