from collections import OrderedDict

import click

from ape.plugins import discovered_plugins, CLI_GROUP_REGISTRATION_FN


def clean_plugin_name(name: str) -> str:
    return name.replace("ape_", "").replace("_", "-")


CLI_PLUGINS = OrderedDict(
    (clean_plugin_name(n), getattr(p, CLI_GROUP_REGISTRATION_FN))
    for n, p in discovered_plugins.items()
    if hasattr(p, CLI_GROUP_REGISTRATION_FN)
)


class ApeCLI(click.MultiCommand):
    def list_commands(self, ctx):
        return list(sorted(n for n in CLI_PLUGINS))

    def get_command(self, ctx, name):
        return CLI_PLUGINS[name]()


@click.command(cls=ApeCLI, context_settings=dict(help_option_names=["-h", "--help"]))
@click.version_option(message="%(version)s")
def cli():
    pass
