from ape import plugins

from .config import Config


@plugins.register(plugins.Config)
def config_class():
    return Config
