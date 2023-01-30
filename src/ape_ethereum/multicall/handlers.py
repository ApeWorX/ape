from typing import Any, Iterator, List, Tuple, Union

from ape.api import ReceiptAPI, TransactionAPI
from ape.contracts.base import (
    ContractCallHandler,
    ContractInstance,
    ContractMethodHandler,
    ContractTransactionHandler,
    _select_method_abi,
)
from ape.exceptions import ChainError
from ape.types import ContractType, HexBytes
from ape.utils import ManagerAccessMixin, cached_property
from ape.utils.abi import MethodABI

from .constants import (
    MULTICALL3_ADDRESS,
    MULTICALL3_CODE,
    MULTICALL3_CONTRACT_TYPE,
    SUPPORTED_CHAINS,
)
from .exceptions import InvalidOption, NotExecutedError, UnsupportedChainError, ValueRequired


class BaseMulticall(ManagerAccessMixin):
    def __init__(self) -> None:
        """
        Initialize a new Multicall session object. By default, there are no calls to make.
        """
        self.calls: List[dict] = []

    @classmethod
    def inject(cls):
        """
        Create the multicall module contract on-chain, so we can use it.
        Must use a provider that supports ``debug_setCode``.

        Usage example::

            from ape_ethereum import multicall

            @pytest.fixture(scope="session")
            def use_multicall():
                # NOTE: use this fixture any test where you want to use a multicall
                multicall.BaseMulticall.deploy()
        """
        active_provider = cls.network_manager.active_provider
        assert active_provider, "Must be connected to an active network to deploy"
        from ape_ethereum import multicall

        active_provider.set_code(
            multicall.constants.MULTICALL3_ADDRESS,
            multicall.constants.MULTICALL3_CODE,
        )
        return multicall

    @cached_property
    def contract(self) -> ContractInstance:
        try:
            # See if we can fetch it from an explorer first
            contract = self.chain_manager.contracts.instance_at(MULTICALL3_ADDRESS)

        except ChainError:
            # else use our backend (with less methods)
            contract = self.chain_manager.contracts.instance_at(
                MULTICALL3_ADDRESS,
                contract_type=ContractType.parse_obj(MULTICALL3_CONTRACT_TYPE),
            )

        if self.provider.chain_id not in SUPPORTED_CHAINS and contract.code != MULTICALL3_CODE:
            # NOTE: 2nd condition allows for use in local test deployments and fork networks
            raise UnsupportedChainError()

        return contract

    @property
    def handler(self) -> ContractTransactionHandler:
        if any(call["value"] > 0 for call in self.calls):
            return self.contract.aggregate3Value

        elif any(call["allowFailure"] for call in self.calls):
            return self.contract.aggregate3

        else:
            return self.contract.aggregate

    def add(
        self,
        call: ContractMethodHandler,
        *args,
        allowFailure: bool = False,
        value: int = 0,
    ):
        """
        Adds a call to the Multicall session object.

        Raises:
            :class:`InvalidOption`: If one of the kwarg modifiers is not able to be used.

        Args:
            call: :class:`ContractMethodHandler` The method to call.
            *args: The arguments to invoke the method with.
            allowFailure: bool Whether the call is allowed to fail.
            value: int The amount of ether to forward with the call.
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
    """

    def __init__(self) -> None:
        super().__init__()

        self.abis: List[MethodABI] = []
        self._result: Union[None, Tuple[int, List[HexBytes]], List[Tuple[bool, HexBytes]]] = None

    @property
    def handler(self) -> ContractCallHandler:  # type: ignore[override]
        return super().handler.call  # NOTE: all Multicall3 methods are mutable calls by default

    def add(self, call: ContractMethodHandler, *args, **kwargs):
        if "value" in kwargs:
            raise InvalidOption("value")

        super().add(call, *args, **kwargs)
        self.abis.append(_select_method_abi(call.abis, args))

    @property
    def returnData(self) -> List[HexBytes]:
        if not self._result:
            raise NotExecutedError()

        elif isinstance(self._result, tuple):
            # Call3[] or Call3Value[]
            return list(r[1] for r in self._result)  # type: ignore[index]

        else:
            # blockNumber: uint256, returnData: Call[]
            return self._result.returnData  # type: ignore[attr-defined]

    def _decode_results(self) -> Iterator[Any]:
        for abi, data in zip(self.abis, self.returnData):
            result = self.provider.network.ecosystem.decode_returndata(abi, data)

            if isinstance(result, (list, tuple)) and len(result) == 1:
                yield result[0]

            else:
                yield result

    def __call__(self, **call_kwargs) -> Iterator[Any]:
        """
        Perform the Multicall call. This call will trigger again every time the ``Call`` object
        is called.

        Raises:
            :class:`~ape_ethereum.multicall.exceptions.UnsupportedChain`:
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

        from ape_ethereum import multicall

        txn = multitxn.Transaction()
        txn.add(contract.myMethod, *call_args)
        txn.add(contract.myMethod, *call_args)
        ...  # Add as many calls as desired to execute
        txn.add(contract.myMethod, *call_args)
        a, b, ..., z = txn(sender=my_signer)  # Sends the multical transaction
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
