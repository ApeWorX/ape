from ape import plugins
from ape.api import ConfigDict


@plugins.register(plugins.Config)
def config_class():
    return ConfigDict
