from ape.plugins import Config, register


@register(Config)
def config_class():
    from ape_console.config import ConsoleConfig

    return ConsoleConfig
