from ape import plugins
from ape.api.config import ConfigEnum, ConfigItem

from ._cli import cli


class EvmVersion(ConfigEnum):
    constaninople = "constaninople"
    istanbul = "istanbul"


class Config(ConfigItem):
    evm_version: EvmVersion = EvmVersion.istanbul

    def validate_config(self):
        self.evm_version = EvmVersion[self.evm_version]


@plugins.register(plugins.Config)
def config_class():
    return Config


@plugins.register(plugins.CliPlugin)
def cli_subcommand():
    return cli
