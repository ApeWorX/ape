from typing import TYPE_CHECKING, Any, Dict, List, Optional, Union

from eth_utils import to_bytes
from ethpm_types import ABI, ContractType

from ape.api import Address, AddressAPI, ProviderAPI, ReceiptAPI, TransactionAPI
from ape.exceptions import ArgumentsLengthError, ProviderNotConnectedError, TransactionError
from ape.logging import logger
from ape.types import AddressType
from ape.utils import dataclass

if TYPE_CHECKING:
    from ape.managers.converters import ConversionManager
    from ape.managers.networks import NetworkManager


@dataclass
class ContractConstructor:
    deployment_bytecode: bytes
    abi: Optional[ABI]
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
    abi: ABI
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
    address: AddressType
    abis: List[ABI]

    def __repr__(self) -> str:
        abis = sorted(self.abis, key=lambda abi: len(abi.inputs))  # type: ignore
        return abis[-1].signature

    def _convert_tuple(self, v: tuple) -> tuple:
        return self.converter.convert(v, tuple)

    def __call__(self, *args, **kwargs) -> Any:
        args = self._convert_tuple(args)
        selected_abi = _select_abi(self.abis, args)
        if not selected_abi:
            raise ArgumentsLengthError()

        return ContractCall(  # type: ignore
            abi=selected_abi,
            address=self.address,
            provider=self.provider,
            converter=self.converter,
        )(*args, **kwargs)


def _select_abi(abis, args):
    selected_abi = None
    for abi in abis:
        if len(args) == len(abi.inputs):
            selected_abi = abi

    return selected_abi


@dataclass
class ContractTransaction:
    abi: ABI
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
    address: AddressType
    abis: List[ABI]

    def __repr__(self) -> str:
        abis = sorted(self.abis, key=lambda abi: len(abi.inputs))  # type: ignore
        return abis[-1].signature

    def _convert_tuple(self, v: tuple) -> tuple:
        return self.converter.convert(v, tuple)

    def __call__(self, *args, **kwargs) -> ReceiptAPI:
        args = self._convert_tuple(args)
        selected_abi = _select_abi(self.abis, args)
        if not selected_abi:
            raise ArgumentsLengthError()

        return ContractTransaction(  # type: ignore
            abi=selected_abi,
            address=self.address,
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
    address: str
    abis: List[ABI]
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
            :class:`~ape.types.AddressType`
        """
        return self._address

    def __dir__(self) -> List[str]:
        """
        Display methods to IPython on ``c.[TAB]`` tab completion.

        Returns:
            List[str]
        """
        return list(super(AddressAPI, self).__dir__()) + [
            abi.name for abi in self._contract_type.abi  # type: ignore
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

        handlers = {
            "events": ContractEvent,
            "calls": ContractCallHandler,
            "transactions": ContractTransactionHandler,
        }

        def get_handler(abi_type: str) -> Any:
            selected_abis = [
                abi for abi in getattr(self._contract_type, abi_type) if abi.name == attr_name
            ]

            if not selected_abis:
                return  # No ABIs found for this type

            kwargs = {
                "provider": self.provider,
                "converter": self._converter,
                "address": self.address,
                "abis": selected_abis,
            }

            try:
                return handlers[abi_type](**kwargs)  # type: ignore

            except Exception as e:
                # NOTE: Just a hack, because `__getattr__` *must* raise `AttributeError`
                raise AttributeError(str(e)) from e

        # Reverse search for the proper handler for this ABI name, if one exists
        for abi_type in handlers:
            handler = get_handler(abi_type)
            if handler:
                return handler
            # else: No ABI found with `attr_name`

        # No ABIs w/ name `attr_name` found at all
        raise AttributeError(f"{self.__class__.__name__} has no attribute '{attr_name}'")


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

    @property
    def _deployment_bytecode(self) -> bytes:
        if (
            self.contract_type.deployment_bytecode
            and self.contract_type.deployment_bytecode.bytecode
        ):
            return to_bytes(hexstr=self.contract_type.deployment_bytecode.bytecode)

        else:
            return b""

    @property
    def _runtime_bytecode(self) -> bytes:
        if self.contract_type.runtime_bytecode and self.contract_type.runtime_bytecode.bytecode:
            return to_bytes(hexstr=self.contract_type.runtime_bytecode.bytecode)

        else:
            return b""

    def __call__(self, *args, **kwargs) -> TransactionAPI:
        args = self._converter.convert(args, tuple)
        constructor = ContractConstructor(  # type: ignore
            abi=self.contract_type.constructor,
            provider=self._provider,
            converter=self._converter,
            deployment_bytecode=self._deployment_bytecode,
        )
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
