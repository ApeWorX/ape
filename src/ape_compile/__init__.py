from ape import plugins
from ape.api import ConfigEnum, PluginConfig


class EvmVersion(ConfigEnum):
    constantinople = "constantinople"
    istanbul = "istanbul"
    paris = "paris"
    shanghai = "shanghai"


class Config(PluginConfig):
    evm_version: EvmVersion = EvmVersion.shanghai
    """
    A base EVM version for compiler plugins to look to
    when their own is missing. **NOTE**: Typically, compiler
    plugins define their own, and not every compiler is EVM compatible.
    This is only used as a global setting for the compilers that
    are EVM compatible.
    """

    include_dependencies: bool = False
    """
    Set to ``True`` to compile dependencies during ``ape compile``.
    Generally, dependencies are not compiled during ``ape compile``
    This is because dependencies may not compile in Ape on their own,
    but you can still reference them in your project's contracts' imports.
    Some projects may be more dependency-based and wish to have the
    contract types always compiled during ``ape compile``, and these projects
    should configure ``include_dependencies`` to be ``True``.
    """

    def validate_config(self):
        self.evm_version = EvmVersion[self.evm_version]


@plugins.register(plugins.Config)
def config_class():
    return Config
