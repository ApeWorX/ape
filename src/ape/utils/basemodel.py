from abc import ABC
from typing import TYPE_CHECKING, Any, ClassVar, Dict, Iterator, List, Optional, Union, cast

from ethpm_types import BaseModel as _BaseModel

from ape.exceptions import ApeAttributeError, ApeIndexError, ProviderNotConnectedError
from ape.logging import logger
from ape.utils.misc import cached_property, singledispatchmethod

if TYPE_CHECKING:
    from ape.api.providers import ProviderAPI
    from ape.managers.accounts import AccountManager
    from ape.managers.chain import ChainManager
    from ape.managers.compilers import CompilerManager
    from ape.managers.config import ConfigManager
    from ape.managers.converters import ConversionManager
    from ape.managers.networks import NetworkManager
    from ape.managers.project import DependencyManager, ProjectManager
    from ape.managers.query import QueryManager
    from ape.plugins import PluginManager
    from ape.pytest.runners import PytestApeRunner


class injected_before_use(property):
    """
    Injected properties are injected class variables that must be set before use.

    **NOTE**: do not appear in a Pydantic model's set of properties.
    """

    def __get__(self, *args):
        arg_strs = []
        for argument in args:
            try:
                arg_str = str(argument)
            except Exception as err:
                logger.debug(f"Failed calling __str__. Exception: {err}")
                arg_strs.append("<?>")
                continue

            arg_strs.append(arg_str)

        error_message = "Value not set"
        if arg_strs:
            error_message = f"{error_message} (arguments={', '.join(arg_strs)})"

        error_message = f"{error_message}. Please inject this property before calling."
        raise ValueError(error_message)


class ManagerAccessMixin:
    # NOTE: cast is used to update the class type returned to mypy
    account_manager: ClassVar["AccountManager"] = cast("AccountManager", injected_before_use())

    chain_manager: ClassVar["ChainManager"] = cast("ChainManager", injected_before_use())

    compiler_manager: ClassVar["CompilerManager"] = cast("CompilerManager", injected_before_use())

    config_manager: ClassVar["ConfigManager"] = cast("ConfigManager", injected_before_use())

    conversion_manager: ClassVar["ConversionManager"] = cast(
        "ConversionManager", injected_before_use()
    )

    dependency_manager: ClassVar["DependencyManager"] = cast(
        "DependencyManager", injected_before_use()
    )

    network_manager: ClassVar["NetworkManager"] = cast("NetworkManager", injected_before_use())

    plugin_manager: ClassVar["PluginManager"] = cast("PluginManager", injected_before_use())

    project_manager: ClassVar["ProjectManager"] = cast("ProjectManager", injected_before_use())

    query_manager: ClassVar["QueryManager"] = cast("QueryManager", injected_before_use())

    _test_runner: ClassVar[Optional["PytestApeRunner"]] = None

    @property
    def provider(self) -> "ProviderAPI":
        """
        The current active provider if connected to one.

        Raises:
            :class:`~ape.exceptions.ProviderNotConnectedError`: When there is
            no active provider at runtime.

        Returns:
            :class:`~ape.api.providers.ProviderAPI`
        """
        if provider := self.network_manager.active_provider:
            return provider

        raise ProviderNotConnectedError()


class BaseInterface(ManagerAccessMixin, ABC):
    """
    Abstract class that has manager access.
    """


def _get_alt(name: str) -> Optional[str]:
    alt = None
    if ("-" not in name and "_" not in name) or ("-" in name and "_" in name):
        alt = None
    elif "-" in name:
        alt = name.replace("-", "_")
    elif "_" in name:
        alt = name.replace("_", "-")

    return alt


class ExtraModelAttributes(_BaseModel):
    """
    A class for defining extra model attributes.
    """

    name: str
    """
    The name of the attributes. This is important
    in instances such as when an attribute is missing,
    we can show a more accurate exception message.
    """

    attributes: Union[Dict[str, Any], "BaseModel"]
    """The attributes."""

    include_getattr: bool = True
    """Whether to use these in ``__getattr__``."""

    include_getitem: bool = False
    """Whether to use these in ``__getitem__``."""

    additional_error_message: Optional[str] = None
    """
    An additional error message to include at the end of
    the normal IndexError message.
    """

    def __contains__(self, name: str) -> bool:
        attr_dict = self.attributes if isinstance(self.attributes, dict) else self.attributes.dict()
        if name in attr_dict:
            return True

        elif alt := _get_alt(name):
            return alt in attr_dict

        return False

    def get(self, name: str) -> Optional[Any]:
        """
        Get an attribute.

        Args:
            name (str): The name of the attribute.

        Returns:
            Optional[Any]: The attribute if it exists, else ``None``.
        """

        res = self._get(name)
        if res is not None:
            return res

        if alt := _get_alt(name):
            res = self._get(alt)
            if res is not None:
                return res

        return None

    def _get(self, name: str) -> Optional[Any]:
        return (
            self.attributes.get(name)
            if isinstance(self.attributes, dict)
            else getattr(self.attributes, name, None)
        )


class BaseModel(_BaseModel):
    """
    An ape-pydantic BaseModel.
    """

    def __ape_extra_attributes__(self) -> Iterator[ExtraModelAttributes]:
        """
        Override this method to supply extra attributes
        to a model in Ape; this allow more properties
        to be available when invoking ``__getattr__``.

        Returns:
            Iterator[:class:`~ape.utils.basemodel.ExtraModelAttributes`]: A
            series of instances defining extra model attributes.
        """
        return iter(())

    def __getattr__(self, name: str) -> Any:
        """
        An overridden ``__getattr__`` implementation that takes into
        account :meth:`~ape.utils.basemodel.BaseModel.__ape_extra_attributes__`.
        """

        try:
            return super().__getattribute__(name)
        except AttributeError:
            extras_checked = set()
            for ape_extra in self.__ape_extra_attributes__():
                if not ape_extra.include_getattr:
                    continue

                if name in ape_extra:
                    # Attribute was found in one of the supplied
                    # extra attributes mappings.
                    return ape_extra.get(name)

                extras_checked.add(ape_extra.name)

            # The error message mentions the alternative mappings,
            # such as a contract-type map.
            message = f"'{repr(self)}' has no attribute '{name}'"
            if extras_checked:
                extras_str = ", ".join(extras_checked)
                message = f"{message}. Also checked '{extras_str}'"

            raise ApeAttributeError(message)

    def __getitem__(self, name: Any) -> Any:
        # For __getitem__, we first try the extra (unlike `__getattr__`).
        extras_checked = set()
        additional_error_messages = {}
        for extra in self.__ape_extra_attributes__():
            if not extra.include_getitem:
                continue

            if name in extra:
                return extra.get(name)

            extras_checked.add(extra.name)

            if extra.additional_error_message:
                additional_error_messages[extra.name] = extra.additional_error_message

        # NOTE: If extras were supplied, the user was expecting it to be
        #   there (unlike __getattr__).
        if extras_checked:
            prefix = f"Unable to find '{name}' in"
            if not additional_error_messages:
                extras_str = ", ".join(extras_checked)
                message = f"{prefix} any of '{extras_str}'."

            else:
                # The class is including additional error messages for the IndexError.
                message = ""
                for extra_checked in extras_checked:
                    additional_message = additional_error_messages.get(extra_checked)
                    suffix = f" {additional_message}" if additional_message else ""
                    sub_message = f"{prefix} '{extra_checked}'.{suffix}"
                    message = f"{message}\n{sub_message}" if message else sub_message

            raise ApeIndexError(message)

        # The user did not supply any extra __getitem__ attributes.
        # Do what you would have normally done.
        return super().__getitem__(name)


class BaseInterfaceModel(BaseInterface, BaseModel):
    """
    An abstract base-class with manager access on a pydantic base model.
    """

    class Config:
        # NOTE: Due to https://github.com/samuelcolvin/pydantic/issues/1241 we have
        # to add this cached property workaround in order to avoid this error:

        #    TypeError: cannot pickle '_thread.RLock' object

        keep_untouched = (cached_property, singledispatchmethod)
        arbitrary_types_allowed = True
        underscore_attrs_are_private = True
        copy_on_model_validation = "none"
        use_enum_values = False

    def __dir__(self) -> List[str]:
        """
        **NOTE**: Should integrate options in IPython tab-completion.
        https://ipython.readthedocs.io/en/stable/config/integrating.html
        """
        # Filter out protected/private members
        return [member for member in super().__dir__() if not member.startswith("_")]
