from collections.abc import Iterator
from functools import cached_property
from types import ModuleType
from typing import Any, Optional, Union

from eth_pydantic_types import HexBytes
from ethpm_types import ContractType

from ape.api.transactions import ReceiptAPI, TransactionAPI
from ape.contracts.base import (
    ContractCallHandler,
    ContractInstance,
    ContractMethodHandler,
    ContractTransactionHandler,
    _select_method_abi,
)
from ape.exceptions import ChainError, DecodingError
from ape.logging import logger
from ape.types.address import AddressType
from ape.utils.abi import MethodABI
from ape.utils.basemodel import ManagerAccessMixin

from .constants import (
    MULTICALL3_ADDRESS,
    MULTICALL3_CODE,
    MULTICALL3_CONTRACT_TYPE,
    SUPPORTED_CHAINS,
)
from .exceptions import InvalidOption, UnsupportedChainError, ValueRequired


class BaseMulticall(ManagerAccessMixin):
    def __init__(
        self,
        address: AddressType = MULTICALL3_ADDRESS,
        supported_chains: Optional[list[int]] = None,
    ) -> None:
        """
        Initialize a new Multicall session object. By default, there are no calls to make.
        """
        self.address = address
        self.supported_chains = supported_chains or SUPPORTED_CHAINS
        self.calls: list[dict] = []

    @classmethod
    def inject(cls) -> ModuleType:
        """
        Create the multicall module contract on-chain, so we can use it.
        Must use a provider that supports ``debug_setCode``.

        Usage example::

            from ape_ethereum import multicall

            @pytest.fixture(scope="session")
            def use_multicall():
                # NOTE: use this fixture any test where you want to use a multicall
                return multicall.BaseMulticall.inject()
        """
        from ape_ethereum import multicall

        provider = cls.network_manager.provider
        provider.set_code(MULTICALL3_ADDRESS, MULTICALL3_CODE)

        if provider.chain_id not in SUPPORTED_CHAINS:
            SUPPORTED_CHAINS.append(provider.chain_id)

        return multicall

    @cached_property
    def contract(self) -> ContractInstance:
        try:
            # NOTE: This will attempt to fetch the contract, such as from an explorer,
            #   if it is not yet cached.
            contract = self.chain_manager.contracts.instance_at(self.address)

        except ChainError:
            # else use our backend (with less methods)
            contract = self.chain_manager.contracts.instance_at(
                MULTICALL3_ADDRESS,
                contract_type=ContractType.model_validate(MULTICALL3_CONTRACT_TYPE),
            )

        if self.provider.chain_id not in self.supported_chains and contract.code != MULTICALL3_CODE:
            # NOTE: 2nd condition allows for use in local test deployments and fork networks
            raise UnsupportedChainError()

        return contract

    @property
    def handler(self) -> ContractTransactionHandler:
        if any(call["value"] > 0 for call in self.calls):
            return self.contract.aggregate3Value

        return self.contract.aggregate3

    def add(
        self,
        call: ContractMethodHandler,
        *args,
        allowFailure: bool = True,
        value: int = 0,
    ) -> "BaseMulticall":
        """
        Adds a call to the Multicall session object.

        Raises:
            :class:`~ape_ethereum.multicall.exceptions.InvalidOption`: If one
              of the kwarg modifiers is not able to be used.

        Args:
            call (:class:`~ape_ethereum.multicall.handlers.ContractMethodHandler`):
              The method to call.
            *args: The arguments to invoke the method with.
            allowFailure (bool): Whether the call is allowed to fail.
            value (int): The amount of ether to forward with the call.

        Returns:
            :class:`~ape_ethereum.multicall.handlers.BaseMulticall`: returns itself
              to emulate a builder pattern.
        """

        # Append call dict to the list
        # NOTE: Depending upon `_handler_method_abi` at time when `__call__` is triggered,
        #       some of these properties will be unused
        self.calls.append(
            {
                "target": call.contract.address,
                "allowFailure": allowFailure,
                "value": value,
                "callData": call.encode_input(*args),
            }
        )
        return self


class Call(BaseMulticall):
    """
    Create a sequence of calls to execute at once using ``eth_call`` via the Multicall3 contract.

    Usage example::

        from ape_ethereum import multicall

        call = multicall.Call()
        call.add(contract.myMethod, *call_args)
        call.add(contract.myMethod, *call_args)
        ...  # Add as many calls as desired
        call.add(contract.myMethod, *call_args)
        a, b, ..., z = call()  # Performs multicall
        # or, using a builder pattern:
        call = multicall.Call()
            .add(contract.myMethod, *call_args)
            .add(contract.myMethod, *call_args)
            ...  # Add as many calls as desired
            .add(contract.myMethod, *call_args)
        a, b, ..., z = call()  # Performs multicall
    """

    def __init__(
        self,
        address: AddressType = MULTICALL3_ADDRESS,
        supported_chains: Optional[list[int]] = None,
    ) -> None:
        super().__init__(address=address, supported_chains=supported_chains)

        self.abis: list[MethodABI] = []
        self._result: Union[None, list[tuple[bool, HexBytes]]] = None

    @property
    def handler(self) -> ContractCallHandler:  # type: ignore[override]
        return super().handler.call  # NOTE: all Multicall3 methods are mutable calls by default

    def add(self, call: ContractMethodHandler, *args, **kwargs):
        if "value" in kwargs:
            raise InvalidOption("value")

        super().add(call, *args, **kwargs)
        self.abis.append(_select_method_abi(call.abis, args))
        return self

    @property
    def returnData(self) -> list[HexBytes]:
        # NOTE: this property is kept camelCase to align with the raw EVM struct
        result = self._result  # Declare for typing reasons.
        return [res.returnData if res.success else None for res in result]  # type: ignore

    def _decode_results(self) -> Iterator[Any]:
        for abi, data in zip(self.abis, self.returnData):
            if data is None:
                # The call failed.
                yield data
                continue

            try:
                result = self.provider.network.ecosystem.decode_returndata(abi, data)
            except DecodingError as err:
                logger.error(err)
                yield data  # Yield the raw data
                continue

            if isinstance(result, (list, tuple)) and len(result) == 1:
                yield result[0]

            else:
                yield result

    def __call__(self, **call_kwargs) -> Iterator[Any]:
        """
        Perform the Multicall call. This call will trigger again every time the ``Call`` object
        is called.

        Raises:
            :class:`~ape_ethereum.multicall.exceptions.UnsupportedChainError`:
              If there is not an instance of Multicall3 deployed
              on the current chain at the expected address.

        Args:
            **call_kwargs: the kwargs to pass through to the call handler.

        Returns:
            Iterator[Any]: the sequence of values produced by performing each call stored
              by this instance.
        """
        self._result = self.handler(self.calls, **call_kwargs)
        return self._decode_results()

    def as_transaction(self, **txn_kwargs) -> TransactionAPI:
        """
        Encode the Multicall transaction as a ``TransactionAPI`` object, but do not execute it.

        Returns:
            :class:`~ape.api.transactions.TransactionAPI`
        """
        return self.handler.as_transaction(self.calls, **txn_kwargs)


class Transaction(BaseMulticall):
    """
    Create a sequence of calls to execute at once using ``eth_sendTransaction``
    via the Multicall3 contract.

    Usage example::

        from ape_ethereum.multicall import Transaction

        txn = Transaction()
        txn.add(contract.myMethod, *call_args)
        txn.add(contract.myMethod, *call_args)
        ...  # Add as many calls as desired to execute
        txn.add(contract.myMethod, *call_args)
        a, b, ..., z = txn(sender=my_signer).return_data  # Sends the multicall transaction
        # or, using a builder pattern:
        txn = Transaction()
            .add(contract.myMethod, *call_args)
            .add(contract.myMethod, *call_args)
            ...  # Add as many calls as desired to execute
            .add(contract.myMethod, *call_args)
        a, b, ..., z = txn(sender=my_signer).return_data  # Sends the multicall transaction
    """

    def _validate_calls(self, **txn_kwargs) -> None:
        required_value = sum(call["value"] for call in self.calls)
        if required_value > 0:
            if "value" not in txn_kwargs:
                raise ValueRequired(required_value)

            value = self.conversion_manager.convert(txn_kwargs["value"], int)

            if required_value < value:
                raise ValueRequired(required_value)

        # NOTE: Won't fail if `value` is provided otherwise (won't do anything either)

    def __call__(self, **txn_kwargs) -> ReceiptAPI:
        """
        Execute the Multicall transaction. The transaction will broadcast again every time
        the ``Transaction`` object is called.

        Raises:
            :class:`UnsupportedChain`: If there is not an instance of Multicall3 deployed
              on the current chain at the expected address.

        Args:
            **txn_kwargs: the kwargs to pass through to the transaction handler.

        Returns:
            :class:`~ape.api.transactions.ReceiptAPI`
        """
        self._validate_calls(**txn_kwargs)
        return self.handler(self.calls, **txn_kwargs)

    def as_transaction(self, **txn_kwargs) -> TransactionAPI:
        """
        Encode the Multicall transaction as a ``TransactionAPI`` object, but do not execute it.

        Returns:
            :class:`~ape.api.transactions.TransactionAPI`
        """
        self._validate_calls(**txn_kwargs)
        return self.handler.as_transaction(self.calls, **txn_kwargs)
