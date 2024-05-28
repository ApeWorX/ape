from pydantic import field_validator

from ape import plugins
from ape.api.config import ConfigEnum, PluginConfig
from ape.utils.misc import SOURCE_EXCLUDE_PATTERNS


class OutputExtras(ConfigEnum):
    """
    Extra stuff you can output. It will
    appear in ``.build/{key.lower()/``
    """

    ABI = "ABI"
    """
    Include this value to output the ABIs of your contracts
    to minified JSONs. This is useful for hosting purposes
    for web-apps.
    """


class Config(PluginConfig):
    """
    Configure general compiler settings.
    """

    exclude: set[str] = set()
    """
    Source exclusion globs across all file types.

    **NOTE**: ``ape.utils.misc.SOURCE_EXCLUDE_PATTERNS`` are automatically
    included in this set.
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

    output_extra: list[OutputExtras] = []
    """
    Extra selections to output. Outputs to ``.build/{key.lower()}``.
    """

    @field_validator("exclude", mode="before")
    @classmethod
    def validate_exclude(cls, value):
        return {*(value or []), *SOURCE_EXCLUDE_PATTERNS}


@plugins.register(plugins.Config)
def config_class():
    return Config
