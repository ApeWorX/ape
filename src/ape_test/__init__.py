from importlib import import_module

from ape import plugins


@plugins.register(plugins.Config)
def config_class():
    from ape_test.config import ApeTestConfig

    return ApeTestConfig


@plugins.register(plugins.AccountPlugin)
def account_types():
    from ape_test.accounts import TestAccount, TestAccountContainer

    return TestAccountContainer, TestAccount


@plugins.register(plugins.ProviderPlugin)
def providers():
    from ape_test.provider import LocalProvider

    yield "ethereum", "local", LocalProvider


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
