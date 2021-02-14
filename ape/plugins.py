from typing import Callable

import importlib
import pkgutil
import click

from .accounts import AccountControllerAPI


CLI_GROUP_REGISTRATION_FN = "ape_get_cli_group"
RegisterCliEndpoint = Callable[[], click.Group]

ACCOUNTS_REGISTRATION_FN = "ape_get_accounts"
RegisterAccounts = Callable[[], AccountControllerAPI]

discovered_plugins = {
    name: importlib.import_module(name)
    for finder, name, ispkg in pkgutil.iter_modules()
    if name.startswith("ape_")
}
