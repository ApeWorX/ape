import re
from re import Pattern
from typing import Union

from pydantic import field_serializer, field_validator

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

    exclude: set[Union[str, Pattern]] = set()
    """
    Source exclusion globs or regex patterns across all file types.
    To use regex, start your values with ``r"`` and they'll be turned
    into regex pattern objects.

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
        given_values = []

        # Convert regex to Patterns.
        for given in value or []:
            if (given.startswith('r"') and given.endswith('"')) or (
                given.startswith("r'") and given.endswith("'")
            ):
                value_clean = given[2:-1]
                pattern = re.compile(value_clean)
                given_values.append(pattern)

            else:
                given_values.append(given)

        # Include defaults.
        return {*given_values, *SOURCE_EXCLUDE_PATTERNS}

    @field_serializer("exclude", when_used="json")
    def serialize_exclude(self, exclude, info):
        """
        Exclude is put back with the weird r-prefix so we can
        go to-and-from.
        """
        result: list[str] = []
        for excl in exclude:
            if isinstance(excl, Pattern):
                result.append(f'r"{excl.pattern}"')
            else:
                result.append(excl)

        return result


@plugins.register(plugins.Config)
def config_class():
    return Config
