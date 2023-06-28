from typing import Any, Optional

from pydantic import Field, validator

from ape import plugins
from ape.api import PluginConfig
from ape.logging import logger


class Config(PluginConfig):
    # TODO: Remove in 0.7
    evm_version: Optional[Any] = Field(None, exclude=True, repr=False)

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

    @validator("evm_version")
    def warn_deprecate(cls, value):
        if value:
            logger.warning(
                "`evm_version` config is deprecated. "
                "Please set in respective compiler plugin config."
            )

        return None


@plugins.register(plugins.Config)
def config_class():
    return Config
