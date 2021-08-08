from ape import plugins

from .providers import LocalNetwork


@plugins.register(plugins.ProviderPlugin)
def providers():
    yield "ethereum", "development", LocalNetwork
