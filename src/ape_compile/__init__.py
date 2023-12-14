from typing import List

from pydantic import field_validator

from ape import plugins
from ape.api import PluginConfig


class Config(PluginConfig):
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

    exclude: List[str] = ["*package.json", "*package-lock.json", "*tsconfig.json"]
    """
    Source exclusion globs across all file types.
    """

    @field_validator("exclude", mode="before")
    @classmethod
    def validate_exclude(cls, value):
        return value or []


@plugins.register(plugins.Config)
def config_class():
    return Config
