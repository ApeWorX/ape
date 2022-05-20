from abc import ABC
from typing import TYPE_CHECKING, ClassVar, Dict, List, cast

from ethpm_types import ContractType
from pydantic import BaseModel

from ape.exceptions import ProviderNotConnectedError
from ape.types import AddressType
from ape.utils.misc import cached_property, singledispatchmethod

if TYPE_CHECKING:
    from ape.api.providers import ProviderAPI
    from ape.contracts.base import ContractContainer, ContractInstance
    from ape.managers.accounts import AccountManager
    from ape.managers.chain import ChainManager
    from ape.managers.compilers import CompilerManager
    from ape.managers.config import ConfigManager
    from ape.managers.converters import ConversionManager
    from ape.managers.networks import NetworkManager
    from ape.managers.project import DependencyManager, ProjectManager
    from ape.managers.query import QueryManager
    from ape.plugins import PluginManager


class injected_before_use(property):
    """
    Injected properties are injected class variables that must be set before use
    **NOTE**: do not appear in a Pydantic model's set of properties.
    """

    def __get__(self, *args):
        raise ValueError("Value not set. Please inject this property before calling.")


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

    @property
    def provider(self) -> "ProviderAPI":
        """
        The current active provider if connected to one.

        Raises:
            :class:`~ape.exceptions.AddressError`: When there is no active
               provider at runtime.

        Returns:
            :class:`~ape.api.providers.ProviderAPI`
        """
        if self.network_manager.active_provider is None:
            raise ProviderNotConnectedError()
        return self.network_manager.active_provider

    def create_contract_container(self, contract_type: ContractType) -> "ContractContainer":
        """
        Helper method for creating a ``ContractContainer``.

        Args:
            contract_type (``ContractType``): Type of contract for the container

        Returns:
            :class:`~ape.contracts.ContractContainer`
        """
        from ape.contracts.base import ContractContainer

        return ContractContainer(contract_type=contract_type)

    def create_contract(
        self, address: "AddressType", contract_type: "ContractType"
    ) -> "ContractInstance":
        """
        Helper method for creating a ``ContractInstance``.

        Args:
            address (``AddressType``): Address of contract
            contract_type (``ContractType``): Type of contract

        Returns:
            :class:`~ape.contracts.ContractInstance`
        """
        from ape.contracts.base import ContractInstance

        return ContractInstance(address=address, contract_type=contract_type)


class BaseInterface(ManagerAccessMixin, ABC):
    """
    Abstract class that has manager access.
    """


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
        anystr_strip_whitespace = True
        copy_on_model_validation = False

    def __dir__(self) -> List[str]:
        """
        NOTE: Should integrate options in IPython tab-completion.
        https://ipython.readthedocs.io/en/stable/config/integrating.html
        """
        # Filter out protected/private members
        return [member for member in super().__dir__() if not member.startswith("_")]

    def dict(self, *args, **kwargs) -> Dict:
        if "by_alias" not in kwargs:
            kwargs["by_alias"] = True

        if "exclude_none" not in kwargs:
            kwargs["exclude_none"] = True

        return super().dict(*args, **kwargs)

    def json(self, *args, **kwargs) -> str:

        if "separators" not in kwargs:
            kwargs["separators"] = (",", ":")

        if "sort_keys" not in kwargs:
            kwargs["sort_keys"] = True

        if "by_alias" not in kwargs:
            kwargs["by_alias"] = True

        if "exclude_none" not in kwargs:
            kwargs["exclude_none"] = True

        return super().json(*args, **kwargs)
