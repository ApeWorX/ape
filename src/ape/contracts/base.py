from typing import TYPE_CHECKING, Any, Dict, List, Optional, Union

from ethpm_types import ContractType
from ethpm_types.abi import ConstructorABI, EventABI, MethodABI

from ape.api import Address, AddressAPI, ProviderAPI, ReceiptAPI, TransactionAPI
from ape.exceptions import (
    ArgumentsLengthError,
    ContractError,
    ProviderNotConnectedError,
    TransactionError,
)
from ape.logging import logger
from ape.types import AddressType
from ape.utils import dataclass

if TYPE_CHECKING:
    from ape.managers.converters import ConversionManager
    from ape.managers.networks import NetworkManager


@dataclass
class ContractConstructor:
    deployment_bytecode: bytes
    abi: ConstructorABI
    provider: ProviderAPI
    converter: "ConversionManager"

    def __post_init__(self):
        if len(self.deployment_bytecode) == 0:
            logger.warning("Deploying an empty contract (no bytecode)")

    def __repr__(self) -> str:
        return self.abi.signature if self.abi else "constructor()"

    def _convert_tuple(self, v: tuple) -> tuple:
        return self.converter.convert(v, tuple)

    def encode(self, *args, **kwargs) -> TransactionAPI:
        args = self._convert_tuple(args)
        kwargs = dict(
            (k, v)
            for k, v in zip(
                kwargs.keys(),
                self._convert_tuple(tuple(kwargs.values())),
            )
        )
        return self.provider.network.ecosystem.encode_deployment(
            self.deployment_bytecode, self.abi, *args, **kwargs
        )

    def __call__(self, *args, **kwargs) -> ReceiptAPI:
        if "sender" in kwargs:
            sender = kwargs["sender"]
            txn = self.encode(*args, **kwargs)
            return sender.call(txn)

        txn = self.encode(*args, **kwargs)
        return self.provider.send_transaction(txn)


@dataclass
class ContractCall:
    abi: MethodABI
    address: AddressType
    provider: ProviderAPI
    converter: "ConversionManager"

    def __repr__(self) -> str:
        return self.abi.signature

    def _convert_tuple(self, v: tuple) -> tuple:
        return self.converter.convert(v, tuple)

    def encode(self, *args, **kwargs) -> TransactionAPI:
        kwargs = dict(
            (k, v)
            for k, v in zip(
                kwargs.keys(),
                self._convert_tuple(tuple(kwargs.values())),
            )
        )
        return self.provider.network.ecosystem.encode_transaction(
            self.address, self.abi, *args, **kwargs
        )

    def __call__(self, *args, **kwargs) -> Any:
        txn = self.encode(*args, **kwargs)
        txn.chain_id = self.provider.network.chain_id

        raw_output = self.provider.send_call(txn)
        tuple_output = self.provider.network.ecosystem.decode_calldata(  # type: ignore
            self.abi,
            raw_output,
        )

        # NOTE: Returns a tuple, so make sure to handle all the cases
        if len(tuple_output) < 2:
            return tuple_output[0] if len(tuple_output) == 1 else None

        # TODO: Handle struct output
        return tuple_output


@dataclass
class ContractCallHandler:
    provider: ProviderAPI
    converter: "ConversionManager"
    contract: "ContractInstance"
    abis: List[MethodABI]

    def __repr__(self) -> str:
        abis = sorted(self.abis, key=lambda abi: len(abi.inputs or []))  # type: ignore
        return abis[-1].signature

    def _convert_tuple(self, v: tuple) -> tuple:
        return self.converter.convert(v, tuple)

    def __call__(self, *args, **kwargs) -> Any:
        if not self.contract.is_contract:
            network = self.provider.network.name
            raise _get_non_contract_error(self.contract.address, network)

        args = self._convert_tuple(args)
        selected_abi = _select_abi(self.abis, args)
        if not selected_abi:
            raise ArgumentsLengthError(len(args))

        return ContractCall(  # type: ignore
            abi=selected_abi,
            address=self.contract.address,
            provider=self.provider,
            converter=self.converter,
        )(*args, **kwargs)


def _select_abi(abis, args):
    args = args or []
    selected_abi = None
    for abi in abis:
        inputs = abi.inputs or []
        if len(args) == len(inputs):
            selected_abi = abi

    return selected_abi


@dataclass
class ContractTransaction:
    abi: MethodABI
    address: AddressType
    provider: ProviderAPI
    converter: "ConversionManager"

    def __repr__(self) -> str:
        return self.abi.signature

    def _convert_tuple(self, v: tuple) -> tuple:
        return self.converter.convert(v, tuple)

    def encode(self, *args, **kwargs) -> TransactionAPI:
        kwargs = dict(
            (k, v)
            for k, v in zip(
                kwargs.keys(),
                self._convert_tuple(tuple(kwargs.values())),
            )
        )
        return self.provider.network.ecosystem.encode_transaction(
            self.address, self.abi, *args, **kwargs
        )

    def __call__(self, *args, **kwargs) -> ReceiptAPI:
        if "sender" in kwargs:
            sender = kwargs["sender"]
            txn = self.encode(*args, **kwargs)
            return sender.call(txn)

        raise TransactionError(message="Must specify a `sender`.")


@dataclass
class ContractTransactionHandler:
    provider: ProviderAPI
    converter: "ConversionManager"
    contract: "ContractInstance"
    abis: List[MethodABI]

    def __repr__(self) -> str:
        abis = sorted(self.abis, key=lambda abi: len(abi.inputs or []))  # type: ignore
        return abis[-1].signature

    def _convert_tuple(self, v: tuple) -> tuple:
        return self.converter.convert(v, tuple)

    def __call__(self, *args, **kwargs) -> ReceiptAPI:
        if not self.contract.is_contract:
            network = self.provider.network.name
            raise _get_non_contract_error(self.contract.address, network)

        args = self._convert_tuple(args)
        selected_abi = _select_abi(self.abis, args)
        if not selected_abi:
            raise ArgumentsLengthError(len(args))

        return ContractTransaction(  # type: ignore
            abi=selected_abi,
            address=self.contract.address,
            provider=self.provider,
            converter=self.converter,
        )(*args, **kwargs)


@dataclass
class ContractLog:
    name: str
    data: Dict[str, Any]


@dataclass
class ContractEvent:
    provider: ProviderAPI
    converter: "ConversionManager"
    contract: "ContractInstance"
    abis: List[EventABI]
    cached_logs: List[ContractLog] = []


class ContractInstance(AddressAPI):
    """
    An interactive instance of a smart contract.
    After you deploy a contract using the :class:`~ape.api.accounts.AccountAPI.deploy` method,
    you get back a contract instance.

    Usage example::

        from ape import accounts, project

        a = accounts.load("alias")  # Load an account by alias
        contract = a.deploy(project.MyContract)  # The result of 'deploy()' is a ContractInstance
    """

    _address: AddressType
    _converter: "ConversionManager"
    _contract_type: ContractType

    def __repr__(self) -> str:
        contract_name = self._contract_type.name or "<Unnamed Contract>"
        return f"<{contract_name} {self.address}>"

    @property
    def address(self) -> AddressType:
        """
        The address of the contract.

        Returns:
            ``AddressType``
        """
        return self._address

    def __dir__(self) -> List[str]:
        """
        Display methods to IPython on ``c.[TAB]`` tab completion.

        Returns:
            List[str]
        """
        return list(super(AddressAPI, self).__dir__()) + [
            abi.name for abi in self._contract_type.abi if isinstance(abi, (MethodABI, EventABI))
        ]

    def __getattr__(self, attr_name: str) -> Any:
        """
        Access a method or property on the contract using ``.`` access.

        Usage example::

            result = contract.vote()  # Implies a method named "vote" exists on the contract.

        Args:
            attr_name (str): The name of the method or property to access.

        Returns:
            any: The return value from the contract call, or a transaction receipt.
        """

        def name_matches(abi):
            return abi.name == attr_name

        selected_view_methods = list(filter(name_matches, self._contract_type.view_methods))
        has_matching_view_methods = len(selected_view_methods) > 0

        selected_mutable_methods = list(filter(name_matches, self._contract_type.mutable_methods))
        has_matching_mutable_methods = len(selected_mutable_methods) > 0

        selected_events = list(filter(name_matches, self._contract_type.events))
        has_matching_events = len(selected_events) > 0

        num_matching_conditions = sum(
            [
                has_matching_view_methods,
                has_matching_mutable_methods,
                has_matching_events,
            ]
        )

        if num_matching_conditions == 0:
            # Didn't find anything that matches
            # NOTE: `__getattr__` *must* raise `AttributeError`
            name = self._contract_type.name or self.__class__.__name__
            raise AttributeError(f"'{name}' has no attribute '{attr_name}'.")

        elif num_matching_conditions > 1:
            # ABI should not contain a mix of events, mutable and view methods that match
            # NOTE: `__getattr__` *must* raise `AttributeError`
            raise AttributeError(f"{self.__class__.__name__} has corrupted ABI.")

        kwargs = {
            "provider": self.provider,
            "converter": self._converter,
            "contract": self,
        }

        # Handle according to the proper abi type handler
        if has_matching_events:
            kwargs["abis"] = selected_events
            handler = ContractEvent

        elif has_matching_view_methods:
            kwargs["abis"] = selected_view_methods
            handler = ContractCallHandler  # type: ignore

        elif has_matching_mutable_methods:
            kwargs["abis"] = selected_mutable_methods
            handler = ContractTransactionHandler  # type: ignore

        try:
            return handler(**kwargs)  # type: ignore

        except Exception as e:
            # NOTE: Just a hack, because `__getattr__` *must* raise `AttributeError`
            raise AttributeError(str(e)) from e


@dataclass
class ContractContainer:
    """
    A wrapper around the contract type that has access to the provider.
    When you import your contracts from the :class:`ape.managers.project.ProjectManager`, you
    are using this class.

    Usage example::

        from ape import project

        contract_container = project.MyContract  # Assuming there is a contract named "MyContract"
    """

    contract_type: ContractType
    """The type of the contract."""

    _provider: Optional[ProviderAPI]
    # _provider is only None when a user is not connected to a provider.

    _converter: "ConversionManager"

    def __repr__(self) -> str:
        return f"<{self.contract_type.name}>"

    def at(self, address: str) -> ContractInstance:
        """
        Get a contract at the given address.

        Usage example::

            from ape import project

            my_contract = project.MyContract.at("0xAbC1230001112223334445566611855443322111")

        Args:
            address (str): The address to initialize a contract.
              **NOTE**: Things will not work as expected if the contract is not actually
              deployed to this address or if the contract at the given address has
              a different ABI than :attr:`~ape.contracts.ContractContainer.contract_type`.

        Returns:
            :class:`~ape.contracts.ContractInstance`
        """

        return ContractInstance(  # type: ignore
            _address=address,
            _provider=self._provider,
            _converter=self._converter,
            _contract_type=self.contract_type,
        )

    def __call__(self, *args, **kwargs) -> TransactionAPI:
        args = self._converter.convert(args, tuple)
        constructor = ContractConstructor(  # type: ignore
            abi=self.contract_type.constructor,
            provider=self._provider,
            converter=self._converter,
            deployment_bytecode=self.contract_type.get_deployment_bytecode() or b"",
        )

        args_length = len(args)
        inputs_length = (
            len(constructor.abi.inputs) if constructor.abi and constructor.abi.inputs else 0
        )
        if inputs_length != args_length:
            raise ArgumentsLengthError(args_length, inputs_length=inputs_length)

        return constructor.encode(*args, **kwargs)


def _Contract(
    address: Union[str, AddressAPI, AddressType],
    networks: "NetworkManager",
    converters: "ConversionManager",
    contract_type: Optional[ContractType] = None,
) -> AddressAPI:
    """
    Function used to triage whether we have a contract type available for
    the given address/network combo, or explicitly provided. If none are found,
    returns a simple ``Address`` instance instead of throwing (provides a warning)
    """
    provider = networks.active_provider
    if not provider:
        raise ProviderNotConnectedError()

    converted_address: AddressType = converters.convert(address, AddressType)

    # Check contract cache (e.g. previously deployed/downloaded contracts)
    # TODO: Add ``contract_cache`` dict-like object to ``NetworkAPI``
    # network = provider.network
    # if not contract_type and address in network.contract_cache:
    #    contract_type = network.contract_cache[address]

    # Check explorer API/cache (e.g. publicly published contracts)
    # TODO: Store in ``NetworkAPI.contract_cache`` to reduce API calls
    explorer = provider.network.explorer
    if not contract_type and explorer:
        contract_type = explorer.get_contract_type(converted_address)

    # We have a contract type either:
    #   1) explicitly provided,
    #   2) from network cache, or
    #   3) from explorer
    if contract_type:
        return ContractInstance(  # type: ignore
            _address=converted_address,
            _provider=provider,
            _converter=converters,
            _contract_type=contract_type,
        )

    else:
        # We don't have a contract type from any source, provide raw address instead
        logger.warning(f"No contract type found for {address}")
        return Address(  # type: ignore
            _address=converted_address,
            _provider=provider,
        )


def _get_non_contract_error(address: str, network_name: str) -> ContractError:
    raise ContractError(
        f"Unable to make contract call. "
        f"'{address}' is not a contract on network '{network_name}'."
    )
