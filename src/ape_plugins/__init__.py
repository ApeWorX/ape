from ape.plugins import Config, register


@register(Config)
def config_class():
    from ape.api.config import ConfigDict

    return ConfigDict
