from typing import Type

from ape.api.accounts import AccountContainerAPI

from .pluggy_patch import hookspec


class AccountPlugin:
    @hookspec
    def accounts_container(self) -> Type[AccountContainerAPI]:
        """
        Must return an Account Container object
        """
