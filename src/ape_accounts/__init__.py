from ape import plugins

from .accounts import AccountContainer


@plugins.register(plugins.AccountPlugin)
def accounts_container():
    return AccountContainer
