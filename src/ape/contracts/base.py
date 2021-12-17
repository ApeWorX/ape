from typing import TYPE_CHECKING, Any, Dict, List, Optional, Union

from eth_utils import to_bytes

from ape.api import Address, AddressAPI, ProviderAPI, ReceiptAPI, TransactionAPI
from ape.exceptions import (
    ArgumentsLengthError,
    ContractDeployError,
    ProviderError,
    TransactionError,
)
from ape.logging import logger
from ape.types import ABI, AddressType, ContractType
from ape.utils import dataclass

if TYPE_CHECKING:
    from ape.managers.converters import ConversionManager
    from ape.managers.networks import NetworkManager


def _encode_address_args(*args):
    # Convert higher level address types to str
    return [arg.address if isinstance(arg, AddressAPI) else arg for arg in args]


def _encode_address_kwargs(**kwargs):
    # Convert higher level address types to str
    return {
        key: value.address if isinstance(value, AddressAPI) else value
        for key, value in kwargs.items()
    }


@dataclass
class ContractConstructor:
    deployment_bytecode: bytes
    abi: Optional[ABI]
    provider: ProviderAPI

    def __post_init__(self):
        if len(self.deployment_bytecode) == 0:
            raise ContractDeployError(message="No bytecode to deploy.")

    def __repr__(self) -> str:
        return self.abi.signature if self.abi else "constructor()"

    def encode(self, *args, **kwargs) -> TransactionAPI:
        return self.provider.network.ecosystem.encode_deployment(
            self.deployment_bytecode,
            self.abi,
            *_encode_address_args(*args),
            **_encode_address_kwargs(**kwargs),
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

    def __repr__(self) -> str:
        return self.abi.signature

    def encode(self, *args, **kwargs) -> TransactionAPI:
        return self.provider.network.ecosystem.encode_transaction(
            self.address, self.abi, *_encode_address_args(*args), **_encode_address_kwargs(**kwargs)
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
    address: AddressType
    abis: List[ABI]

    def __repr__(self) -> str:
        abis = sorted(self.abis, key=lambda abi: len(abi.inputs))
        return abis[-1].signature

    def __call__(self, *args, **kwargs) -> Any:
        selected_abi = _select_abi(self.abis, args)
        if not selected_abi:
            raise ArgumentsLengthError()

        return ContractCall(  # type: ignore
            abi=selected_abi,
            address=self.address,
            provider=self.provider,
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

    def __repr__(self) -> str:
        return self.abi.signature

    def encode(self, *args, **kwargs) -> TransactionAPI:
        return self.provider.network.ecosystem.encode_transaction(
            self.address, self.abi, *_encode_address_args(*args), **_encode_address_kwargs(**kwargs)
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
    address: AddressType
    abis: List[ABI]

    def __repr__(self) -> str:
        abis = sorted(self.abis, key=lambda abi: len(abi.inputs))
        return abis[-1].signature

    def __call__(self, *args, **kwargs) -> ReceiptAPI:
        selected_abi = _select_abi(self.abis, args)
        if not selected_abi:
            raise ArgumentsLengthError()

        return ContractTransaction(  # type: ignore
            abi=selected_abi,
            address=self.address,
            provider=self.provider,
        )(*args, **kwargs)


@dataclass
class ContractLog:
    name: str
    data: Dict[str, Any]


@dataclass
class ContractEvent:
    provider: ProviderAPI
    address: str
    abis: List[ABI]
    cached_logs: List[ContractLog] = []


class ContractInstance(AddressAPI):
    _address: AddressType
    _contract_type: ContractType

    def __repr__(self) -> str:
        return f"<{self._contract_type.contractName} {self.address}>"

    @property
    def address(self) -> AddressType:
        return self._address

    def __dir__(self) -> List[str]:
        # This displays methods to IPython on `c.[TAB]` tab completion
        return list(super(AddressAPI, self).__dir__()) + [
            abi.name for abi in self._contract_type.abi
        ]

    def __getattr__(self, attr_name: str) -> Any:
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
    contract_type: ContractType
    _provider: Optional[ProviderAPI]
    # _provider is only None when a user is not connected to a provider.

    def __repr__(self) -> str:
        return f"<{self.contract_type.contractName}>"

    def at(self, address: str) -> ContractInstance:
        return ContractInstance(  # type: ignore
            _address=address,
            _provider=self._provider,
            _contract_type=self.contract_type,
        )

    @property
    def _deployment_bytecode(self) -> bytes:
        if self.contract_type.deploymentBytecode and self.contract_type.deploymentBytecode.bytecode:
            return to_bytes(hexstr=self.contract_type.deploymentBytecode.bytecode)

        else:
            return b""

    @property
    def _runtime_bytecode(self) -> bytes:
        if self.contract_type.runtimeBytecode and self.contract_type.runtimeBytecode.bytecode:
            return to_bytes(hexstr=self.contract_type.runtimeBytecode.bytecode)

        else:
            return b""

    def __call__(self, *args, **kwargs) -> TransactionAPI:
        constructor = ContractConstructor(  # type: ignore
            abi=self.contract_type.constructor,
            provider=self._provider,
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
        raise ProviderError("Not connected to a network")
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
            _contract_type=contract_type,
        )

    else:
        # We don't have a contract type from any source, provide raw address instead
        logger.warning(f"No contract type found for {address}")
        return Address(  # type: ignore
            _address=converted_address,
            _provider=provider,
        )
