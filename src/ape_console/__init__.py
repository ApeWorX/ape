from ape import plugins
from ape_console.config import ConsoleConfig


@plugins.register(plugins.Config)
def config_class():
    return ConsoleConfig
