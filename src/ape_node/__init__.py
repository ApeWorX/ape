from ape import plugins


@plugins.register(plugins.Config)
def config_class():
    from ape_node.provider import EthereumNodeConfig

    return EthereumNodeConfig


@plugins.register(plugins.ProviderPlugin)
def providers():
    from ape_node.provider import EthereumNetworkConfig, GethDev, Node

    networks_dict = EthereumNetworkConfig().model_dump()
    networks_dict.pop("local")
    for network_name in networks_dict:
        yield "ethereum", network_name, Node

    yield "ethereum", "local", GethDev


@plugins.register(plugins.QueryPlugin)
def query_engines():
    from ape_node.query import OtterscanQueryEngine

    yield OtterscanQueryEngine


def __getattr__(name: str):
    if name == "OtterscanQueryEngine":
        from ape_node.query import OtterscanQueryEngine

        return OtterscanQueryEngine

    import ape_node.provider as module

    return getattr(module, name)


__all__ = [
    "EthereumNetworkConfig",
    "EthereumNodeConfig",
    "GethDev",
    "Node",
    "OtterscanQueryEngine",
]
