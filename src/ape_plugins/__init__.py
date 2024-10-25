from ape import plugins
from ape.api.config import ConfigDict


@plugins.register(plugins.Config)
def config_class():
    return ConfigDict
