from typing import Tuple, Type

from ape.api.accounts import AccountAPI, AccountContainerAPI

from .pluggy_patch import hookspec


class AccountPlugin:
    @hookspec
    def account_types(self) -> Tuple[Type[AccountContainerAPI], Type[AccountAPI]]:
        """
        Must return an Account Container object
        """
