from importlib import import_module
from typing import Any


def __getattr__(name: str) -> Any:
    if name == "AccountManager":
        module = import_module("ape.managers.accounts")
        return module.AccountManager

    elif name == "ChainManager":
        module = import_module("ape.managers.chain")
        return module.ChainManager

    elif name == "CompilerManager":
        module = import_module("ape.managers.compilers")
        return module.CompilerManager

    elif name == "ConfigManager":
        module = import_module("ape.managers.config")
        return module.ConfigManager

    elif name == "ConversionManager":
        module = import_module("ape.managers.converters")
        return module.ConversionManager

    elif name == "NetworkManager":
        module = import_module("ape.managers.networks")
        return module.NetworkManager

    elif name == "PluginManager":
        module = import_module("ape.managers.plugins")
        return module.PluginManager

    elif name == "ProjectManager":
        module = import_module("ape.managers.project")
        return module.ProjectManager

    elif name == "QueryManager":
        module = import_module("ape.managers.query")
        return module.QueryManager

    else:
        raise AttributeError(name)
