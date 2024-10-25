from importlib import import_module

from ape import plugins


@plugins.register(plugins.Config)
def config_class():
    module = import_module("ape_test.config")
    return module.ApeTestConfig


@plugins.register(plugins.AccountPlugin)
def account_types():
    module = import_module("ape_test.accounts")
    return module.TestAccountContainer, module.TestAccount


@plugins.register(plugins.ProviderPlugin)
def providers():
    module = import_module("ape_test.provider")
    yield "ethereum", "local", module.LocalProvider


def __getattr__(name: str):
    if name in ("TestAccountContainer", "TestAccount"):
        module = import_module("ape_test.accounts")
    elif name in (
        "EthTesterProviderConfig",
        "GasExclusion",
        "GasConfig",
        "CoverageReportsConfig",
        "CoverageConfig",
        "ApeTestConfig",
    ):
        module = import_module("ape_test.config")
    else:
        module = import_module("ape_test.provider")

    return getattr(module, name)


__all__ = [
    "TestAccountContainer",
    "TestAccount",
    "EthTesterProviderConfig",
    "LocalProvider",
    "GasConfig",
    "GasExclusion",
    "CoverageReportsConfig",
    "CoverageConfig",
    "ApeTestConfig",
]
