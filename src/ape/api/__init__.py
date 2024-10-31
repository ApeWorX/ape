def __getattr__(name: str):
    if name in (
        "AccountAPI",
        "AccountContainerAPI",
        "ImpersonatedAccount",
        "TestAccountAPI",
        "TestAccountContainerAPI",
    ):
        import ape.api.accounts as accounts_module

        return getattr(accounts_module, name)

    elif name in ("Address",):
        import ape.api.address as address_module

        return getattr(address_module, name)

    elif name in ("CompilerAPI",):
        import ape.api.compiler as compiler_module

        return getattr(compiler_module, name)

    elif name in ("ConfigDict", "ConfigEnum", "PluginConfig"):
        import ape.api.config as config_module

        return getattr(config_module, name)

    elif name in ("ConverterAPI",):
        import ape.api.convert as convert_module

        return getattr(convert_module, name)

    elif name in ("ExplorerAPI",):
        import ape.api.explorers as explorer_module

        return getattr(explorer_module, name)

    elif name in ("BlockAPI, ProviderAPI, SubprocessProvider, TestProviderAPI, UpstreamProvider"):
        import ape.api.providers as provider_module

        return getattr(provider_module, name)

    elif name in (
        "EcosystemAPI",
        "ForkedNetworkAPI",
        "NetworkAPI",
        "ProviderContextManager",
        "create_network_type",
    ):
        import ape.api.networks as network_module

        return getattr(network_module, name)

    elif name in ("DependencyAPI", "ProjectAPI"):
        import ape.api.projects as project_module

        return getattr(project_module, name)

    elif name in ("QueryAPI", "QueryType"):
        import ape.api.query as query_module

        return getattr(query_module, name)

    elif name in ("TraceAPI",):
        import ape.api.trace as trace_module

        return getattr(trace_module, name)

    elif name in ("ReceiptAPI", "TransactionAPI"):
        import ape.api.transactions as tx_module

        return getattr(tx_module, name)

    else:
        raise AttributeError(name)


__all__ = [
    "AccountAPI",
    "AccountContainerAPI",
    "Address",
    "BlockAPI",
    "CompilerAPI",
    "ConfigDict",
    "ConfigEnum",
    "ConverterAPI",
    "create_network_type",
    "DependencyAPI",
    "EcosystemAPI",
    "ExplorerAPI",
    "ForkedNetworkAPI",
    "ImpersonatedAccount",
    "PluginConfig",
    "ProjectAPI",
    "ProviderAPI",
    "ProviderContextManager",
    "QueryType",
    "QueryAPI",
    "NetworkAPI",
    "ReceiptAPI",
    "SubprocessProvider",
    "TestAccountAPI",
    "TestAccountContainerAPI",
    "TestProviderAPI",
    "TraceAPI",
    "TransactionAPI",
    "UpstreamProvider",
]
