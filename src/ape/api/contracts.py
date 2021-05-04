from typing import List, Type, Union

from eth_utils import to_bytes

from ape.types import ContractType

from .address import AddressAPI
from .base import abstractdataclass, abstractmethod, dataclass
from .providers import ProviderAPI, TransactionAPI


@abstractdataclass
class ContractConstructorAPI:
    deployment_bytecode: bytes
    inputs: List[dict] = []
    provider: ProviderAPI

    @abstractmethod
    def __call__(self, *args, **kwargs) -> TransactionAPI:
        ...


@abstractdataclass
class ContractCallAPI:
    name: str
    inputs: List[dict]
    outputs: List[dict]
    provider: ProviderAPI

    @abstractmethod
    def __call__(self, *args, **kwargs) -> TransactionAPI:
        ...


@abstractdataclass
class ContractTransactionAPI:
    name: str
    payable: bool
    inputs: List[dict]
    outputs: List[dict]
    provider: ProviderAPI

    @abstractmethod
    def __call__(self, *args, **kwargs) -> TransactionAPI:
        ...


@abstractdataclass
class ContractEventAPI:
    name: str
    inputs: List[dict]
    provider: ProviderAPI

    @abstractmethod
    def decode(self, data: bytes) -> dict:
        ...


class ContractInstance(AddressAPI):
    address: str
    provider: ProviderAPI
    contract_type: ContractType

    @property
    def event_class(self) -> Type[ContractEventAPI]:
        return self.provider.network.ecosystem.contract_event_class

    @property
    def call_class(self) -> Type[ContractCallAPI]:
        return self.provider.network.ecosystem.contract_call_class

    @property
    def transaction_class(self) -> Type[ContractTransactionAPI]:
        return self.provider.network.ecosystem.contract_transaction_class

    def __getattr__(
        self, attr_name: str
    ) -> Union[ContractEventAPI, ContractCallAPI, ContractTransactionAPI]:
        if attr_name in self.contract_type.events:
            return self.event_class(  # type: ignore
                provider=self.provider,
                **self.contract_type.events[attr_name],  # type: ignore
            )

        elif attr_name in self.contract_type.calls:
            return self.call_class(  # type: ignore
                provider=self.provider,
                **self.contract_type.calls[attr_name],  # type: ignore
            )

        elif attr_name in self.contract_type.transactions:
            return self.transaction_class(  # type: ignore
                provider=self.provider,
                **self.contract_type.transactions[attr_name],  # type: ignore
            )

        else:
            raise AttributeError(f"{self.__class__.__name__} has no attribute '{attr_name}'")


@dataclass
class ContractContainer:
    provider: ProviderAPI
    contract_type: ContractType

    @property
    def constructor_class(self) -> Type[ContractConstructorAPI]:
        return self.provider.network.ecosystem.contract_constructor_class

    @property
    def deployment_bytecode(self) -> bytes:
        if self.contract_type.deploymentBytecode and self.contract_type.deploymentBytecode.bytecode:
            return to_bytes(hexstr=self.contract_type.deploymentBytecode.bytecode)

        else:
            return b""

    @property
    def runtime_bytecode(self) -> bytes:
        if self.contract_type.runtimeBytecode and self.contract_type.runtimeBytecode.bytecode:
            return to_bytes(hexstr=self.contract_type.runtimeBytecode.bytecode)

        else:
            return b""

    def build_deployment(self, *args, **kwargs) -> TransactionAPI:
        constructor = self.constructor_class(  # type: ignore
            provider=self.provider,
            deployment_bytecode=self.deployment_bytecode,
            **self.contract_type.constructor,
        )
        return constructor(*args, **kwargs)
