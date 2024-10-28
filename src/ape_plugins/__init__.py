from ape.plugins import register, Config


@register(Config)
def config_class():
    from ape.api.config import ConfigDict

    return ConfigDict
