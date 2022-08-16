from itertools import islice
from typing import Any, Dict, Iterator, List, Optional, Tuple, Union

import click
import pandas as pd
from ethpm_types import ContractType
from ethpm_types.abi import ConstructorABI, EventABI, MethodABI
from hexbytes import HexBytes

from ape.api import AccountAPI, ReceiptAPI, TransactionAPI
from ape.api.address import BaseAddress
from ape.api.query import ContractEventQuery
from ape.exceptions import ArgumentsLengthError, ChainError, ContractError
from ape.logging import logger
from ape.types import AddressType, ContractLog, LogFilter
from ape.utils import ManagerAccessMixin, cached_property, singledispatchmethod


def _convert_kwargs(kwargs, converter) -> Dict:
    fields = TransactionAPI.__fields__
    kwargs_to_convert = {k: v for k, v in kwargs.items() if k == "sender" or k in fields}
    converted_fields = {
        k: converter(
            v,
            # TODO: Upstream, `TransactionAPI.sender` should be `AddressType` (not `str`)
            AddressType if k == "sender" else fields[k].type_,
        )
        for k, v in kwargs_to_convert.items()
    }
    return {**kwargs, **converted_fields}


class ContractConstructor(ManagerAccessMixin):
    def __init__(
        self,
        deployment_bytecode: HexBytes,
        abi: ConstructorABI,
    ) -> None:
        self.deployment_bytecode = deployment_bytecode
        self.abi = abi

        if not self.deployment_bytecode:
            logger.warning("Deploying an empty contract (no bytecode)")
            self.deployment_bytecode = HexBytes("")

    def __repr__(self) -> str:
        return self.abi.signature if self.abi else "constructor()"

    def serialize_transaction(self, *args, **kwargs) -> TransactionAPI:
        args = self.conversion_manager.convert(args, tuple)
        kwargs = _convert_kwargs(kwargs, self.conversion_manager.convert)
        return self.provider.network.ecosystem.encode_deployment(
            self.deployment_bytecode, self.abi, *args, **kwargs
        )

    def __call__(self, *args, **kwargs) -> ReceiptAPI:
        txn = self.serialize_transaction(*args, **kwargs)

        if "sender" in kwargs and isinstance(kwargs["sender"], AccountAPI):
            sender = kwargs["sender"]
            return sender.call(txn)

        return self.provider.send_transaction(txn)


class ContractCall(ManagerAccessMixin):
    def __init__(self, abi: MethodABI, address: AddressType) -> None:
        super().__init__()
        self.abi = abi
        self.address = address

    def __repr__(self) -> str:
        return self.abi.signature

    def serialize_transaction(self, *args, **kwargs) -> TransactionAPI:
        kwargs = _convert_kwargs(kwargs, self.conversion_manager.convert)
        return self.provider.network.ecosystem.encode_transaction(
            self.address, self.abi, *args, **kwargs
        )

    def __call__(self, *args, **kwargs) -> Any:
        txn = self.serialize_transaction(*args, **kwargs)
        txn.chain_id = self.provider.network.chain_id
        raw_output = self.provider.send_call(txn, **kwargs)
        output = self.provider.network.ecosystem.decode_returndata(
            self.abi,
            raw_output,
        )

        if not isinstance(output, (list, tuple)):
            return output

        # NOTE: Returns a tuple, so make sure to handle all the cases
        elif len(output) < 2:
            return output[0] if len(output) == 1 else None

        return output


class ContractCallHandler(ManagerAccessMixin):

    contract: "ContractInstance"
    abis: List[MethodABI]

    def __init__(self, contract: "ContractInstance", abis: List[MethodABI]) -> None:
        super().__init__()
        self.contract = contract
        self.abis = abis

    def __repr__(self) -> str:
        abis = sorted(self.abis, key=lambda abi: len(abi.inputs or []))
        return abis[-1].signature

    def _convert_tuple(self, v: tuple) -> tuple:
        return self.conversion_manager.convert(v, tuple)

    def __call__(self, *args, **kwargs) -> Any:
        if not self.contract.is_contract:
            network = self.provider.network.name
            raise _get_non_contract_error(self.contract.address, network)

        args = self._convert_tuple(args)
        selected_abi = _select_method_abi(self.abis, args)

        return ContractCall(  # type: ignore
            abi=selected_abi,
            address=self.contract.address,
        )(*args, **kwargs)

    def as_transaction(self, *args, **kwargs):
        """
        Convert the call to a transaction. This is useful for checking coverage
        or checking gas costs.

        Args:
            *args: The contract method invocation arguments.
            **kwargs: Transaction kwargs, such as value or
              sender.

        Returns:
            :class:`~ape.api.transactions.TransactionAPI`
        """
        return self.transact.as_transaction(*args, **kwargs)

    @property
    def transact(self) -> "ContractTransactionHandler":
        """
        Send the call as a transaction.
        """

        return ContractTransactionHandler(self.contract, self.abis)

    def estimate_gas_cost(self, *args, **kwargs) -> int:
        """
        Get the estimated gas cost (according to the provider) for the
        contract method call (as if it were a transaction).

        Args:
            *args: The contract method invocation arguments.
            **kwargs: Transaction kwargs, such as value or
              sender.

        Returns:
            int: The estimated cost of gas to execute the transaction
            reported in the fee-currency's smallest unit, e.g. Wei.
        """

        arguments = self.conversion_manager.convert(args, tuple)
        return self.transact.estimate_gas_cost(*arguments, **kwargs)


def _select_method_abi(abis: List[MethodABI], args: Union[Tuple, List]) -> MethodABI:
    args = args or []
    selected_abi = None
    for abi in abis:
        inputs = abi.inputs or []
        if len(args) == len(inputs):
            selected_abi = abi

    if not selected_abi:
        raise ArgumentsLengthError(len(args))

    return selected_abi


class ContractTransaction(ManagerAccessMixin):

    abi: MethodABI
    address: AddressType

    def __init__(self, abi: MethodABI, address: AddressType) -> None:
        super().__init__()
        self.abi = abi
        self.address = address

    def __repr__(self) -> str:
        return self.abi.signature

    def serialize_transaction(self, *args, **kwargs) -> TransactionAPI:
        if "sender" in kwargs and isinstance(kwargs["sender"], ContractInstance):
            # Automatically impersonate contracts (if API available) when sender
            kwargs["sender"] = self.account_manager.test_accounts[kwargs["sender"].address]

        kwargs = _convert_kwargs(kwargs, self.conversion_manager.convert)
        return self.provider.network.ecosystem.encode_transaction(
            self.address, self.abi, *args, **kwargs
        )

    def __call__(self, *args, **kwargs) -> ReceiptAPI:
        txn = self.serialize_transaction(*args, **kwargs)

        if "sender" in kwargs and isinstance(kwargs["sender"], AccountAPI):
            return kwargs["sender"].call(txn)

        return self.provider.send_transaction(txn)


class ContractTransactionHandler(ManagerAccessMixin):
    def __init__(self, contract: "ContractInstance", abis: List[MethodABI]) -> None:
        super().__init__()
        self.contract = contract
        self.abis = abis

    def __repr__(self) -> str:
        abis = sorted(self.abis, key=lambda abi: len(abi.inputs or []))
        return abis[-1].signature

    def as_transaction(self, *args, **kwargs) -> TransactionAPI:
        """
        Get a :class:`~ape.api.transactions.TransactionAPI`
        for this contract method invocation. This is useful
        for simulations or estimating fees without sending
        the transaction.

        Args:
            *args: The contract method invocation arguments.
            **kwargs: Transaction kwargs, such as value or
              sender.

        Returns:
            :class:`~ape.api.transactions.TransactionAPI`
        """

        contract_transaction = self._as_transaction(*args)
        transaction = contract_transaction.serialize_transaction(*args, **kwargs)
        self.provider.prepare_transaction(transaction)
        return transaction

    def estimate_gas_cost(self, *args, **kwargs) -> int:
        """
        Get the estimated gas cost (according to the provider) for the
        contract method-invocation transaction.

        Args:
            *args: The contract method invocation arguments.
            **kwargs: Transaction kwargs, such as value or
              sender.

        Returns:
            int: The estimated cost of gas to execute the transaction
            reported in the fee-currency's smallest unit, e.g. Wei.
        """
        arguments = self.conversion_manager.convert(args, tuple)
        txn = self.as_transaction(*arguments, **kwargs)
        return self.provider.estimate_gas_cost(txn)

    @property
    def call(self) -> ContractCallHandler:
        """
        Get the :class:`~ape.contracts.base.ContractCallHandler` equivalent
        of this transaction handler. The call-handler uses the ``eth_call``
        RPC under-the-hood and thus it gets reverted before submitted.
        This a useful way to simulate a transaction without invoking it.
        """

        return ContractCallHandler(self.contract, self.abis)

    def _convert_tuple(self, v: tuple) -> tuple:
        return self.conversion_manager.convert(v, tuple)

    def __call__(self, *args, **kwargs) -> ReceiptAPI:
        function_arguments = self._convert_tuple(args)
        contract_transaction = self._as_transaction(*function_arguments)
        return contract_transaction(*function_arguments, **kwargs)

    def _as_transaction(self, *args) -> ContractTransaction:
        if not self.contract.is_contract:
            network = self.provider.network.name
            raise _get_non_contract_error(self.contract.address, network)

        args = self._convert_tuple(args)
        selected_abi = _select_method_abi(self.abis, args)

        return ContractTransaction(  # type: ignore
            abi=selected_abi,
            address=self.contract.address,
        )


class ContractEvent(ManagerAccessMixin):
    """
    The types of events on a :class:`~ape.contracts.base.ContractInstance`.
    Use the event types via ``.`` access on the contract instances.

    Usage example::

         # 'my_contract' refers to a ContractInstance in this case.
         my_event_type = my_contract.MyEvent
    """

    def __init__(
        self,
        contract: "ContractInstance",
        abi: EventABI,
        cached_logs: List[ContractLog] = None,
    ) -> None:
        super().__init__()
        self.contract = contract
        self.abi = abi
        self.cached_logs = cached_logs or []

    def __repr__(self):
        return self.abi.signature

    @property
    def name(self) -> str:
        """
        The name of the contract event, as defined in the contract.
        """

        return self.abi.name

    def __iter__(self) -> Iterator[ContractLog]:
        """
        Get all logs that have occurred for this event.
        """

        yield from self.range(self.chain_manager.blocks.height + 1)

    @property
    def log_filter(self):
        return LogFilter.from_event(
            event=self.abi, addresses=[self.contract.address], start_block=0
        )

    @singledispatchmethod
    def __getitem__(self, value) -> Union[ContractLog, List[ContractLog]]:
        raise NotImplementedError(f"Cannot use '{type(value)}' to access logs.")

    @__getitem__.register
    def __getitem_int(self, index: int) -> ContractLog:
        """
        Access events on the contract by the index of when they occurred.

        Args:
            index (int): The index such that ``0`` is the first log to have occurred
              and ``-1`` is the last.

        Returns:
            :class:`~ape.contracts.base.ContractLog`
        """
        logs = self.provider.get_contract_logs(self.log_filter)
        try:
            if index == 0:
                return next(logs)
            elif index > 0:
                return next(islice(logs, index, index + 1))
            else:
                return list(logs)[index]
        except (IndexError, StopIteration) as err:
            raise IndexError(f"No log at index '{index}' for event '{self.abi.name}'.") from err

    @__getitem__.register
    def __getitem_slice(self, value: slice) -> List[ContractLog]:
        """
        Access a slice of logs from this event.

        Args:
            value (slice): The range of log to get, e.g. ``[5:10]``.

        Returns:
            Iterator[:class:`~ape.contracts.base.ContractLog`]
        """
        logs = self.provider.get_contract_logs(self.log_filter)
        return list(islice(logs, value.start, value.stop, value.step))

    def __len__(self):
        logs = self.provider.get_contract_logs(self.log_filter)
        return sum(1 for _ in logs)

    def query(
        self,
        *columns: List[str],
        start_block: int = 0,
        stop_block: Optional[int] = None,
        step: int = 1,
        engine_to_use: Optional[str] = None,
    ) -> pd.DataFrame:
        """
        Iterate through blocks for log events

        Args:
            columns (List[str]): columns in the DataFrame to return
            start_block (int): The first block, by number, to include in the
              query. Defaults to 0.
            stop_block (Optional[int]): The last block, by number, to include
              in the query. Defaults to the latest block.
            step (int): The number of blocks to iterate between block numbers.
              Defaults to ``1``.
            engine_to_use (Optional[str]): query engine to use, bypasses query
              engine selection algorithm.

        Returns:
            pd.DataFrame
        """

        if start_block < 0:
            start_block = self.chain_manager.blocks.height + start_block

        if stop_block is None:
            stop_block = self.chain_manager.blocks.height

        elif stop_block < 0:
            stop_block = self.chain_manager.blocks.height + stop_block

        elif stop_block > self.chain_manager.blocks.height:
            raise ChainError(
                f"'stop={stop_block}' cannot be greater than "
                f"the chain length ({self.chain_manager.blocks.height})."
            )

        if columns[0] == "*":
            columns = list(ContractLog.__fields__)  # type: ignore

        contract_event_query = ContractEventQuery(
            columns=columns,
            contract=self.contract.address,
            event=self.abi,
            start_block=start_block,
            stop_block=stop_block,
            step=step,
        )
        contract_events = self.query_manager.query(
            contract_event_query, engine_to_use=engine_to_use
        )
        return pd.DataFrame(
            columns=contract_event_query.columns, data=[val.dict() for val in contract_events]
        )

    def range(
        self,
        start_or_stop: int,
        stop: Optional[int] = None,
        search_topics: Optional[Dict[str, Any]] = None,
        extra_addresses: Optional[List] = None,
    ) -> Iterator[ContractLog]:
        """
        Search through the logs for this event using the given filter parameters.

        Args:
            start_or_stop (int): When also given ``stop``, this is the the
              earliest block number in the desired log set.
              Otherwise, it is the total amount of blocks to get starting from ``0``.
            stop (Optional[int]): The latest block number in the
              desired log set. Defaults to delegating to provider.
            search_topics (Optional[Dict]): Search topics, such as indexed event inputs,
              to query by. Defaults to getting all events.
            extra_addresses (Optional[List[``AddressType``]]): Additional contract
              addresses containing the same event type. Defaults to only looking at
              the contract instance where this event is defined.

        Returns:
            Iterator[:class:`~ape.contracts.base.ContractLog`]
        """

        start_block = None
        stop_block = None

        if stop is None:
            start_block = 0
            stop_block = start_or_stop
        elif start_or_stop is not None and stop is not None:
            start_block = start_or_stop
            stop_block = stop - 1

        stop_block = min(stop_block, self.chain_manager.blocks.height)

        addresses = set([self.contract.address] + (extra_addresses or []))
        contract_event_query = ContractEventQuery(
            columns=list(ContractLog.__fields__.keys()),
            contract=addresses,
            event=self.abi,
            search_topics=search_topics,
            start_block=start_block,
            stop_block=stop_block,
        )
        yield from self.query_manager.query(contract_event_query)  # type: ignore

    def from_receipt(self, receipt: ReceiptAPI) -> Iterator[ContractLog]:
        """
        Get all the events from the given receipt.

        Args:
            receipt (:class:`~ape.api.transactions.ReceiptAPI`): The receipt containing the logs.

        Returns:
            Iterator[:class:`~ape.contracts.base.ContractLog`]
        """
        ecosystem = self.provider.network.ecosystem
        yield from ecosystem.decode_logs(receipt.logs, self.abi)

    def poll_logs(
        self,
        start_block: Optional[int] = None,
        stop_block: Optional[int] = None,
        required_confirmations: Optional[int] = None,
        new_block_timeout: Optional[int] = None,
    ) -> Iterator[ContractLog]:
        """
        Poll new blocks. Optionally set a start block to include historical blocks.
        **NOTE**: This is a daemon method; it does not terminate unless an exception occurrs.

        Usage example::

            from ape import chain

            for new_block in chain.blocks.poll_blocks():
                print(f"New block found: number={new_block.number}")

        Args:
            start_block (Optional[int]): The block number to start with. Defaults to the pending
              block number.
            stop_block (Optional[int]): Optionally set a future block number to stop at.
              Defaults to never-ending.
            required_confirmations (Optional[int]): The amount of confirmations to wait
              before yielding the block. The more confirmations, the less likely a reorg will occur.
              Defaults to the network's configured required confirmations.
            new_block_timeout (Optional[int]): The amount of time to wait for a new block before
              quitting. Defaults to 10 seconds for local networks or ``50 * block_time`` for live
              networks.

        Returns:
            Iterator[:class:`~ape.types.ContractLog`]
        """

        required_confirmations = (
            required_confirmations or self.provider.network.required_confirmations
        )

        for new_block in self.chain_manager.blocks.poll_blocks(
            start_block=start_block,
            stop_block=stop_block,
            required_confirmations=required_confirmations,
            new_block_timeout=new_block_timeout,
        ):
            if new_block.number is None:
                continue

            # Get all events in the new block.
            yield from self.range(new_block.number, stop=new_block.number + 1)


class ContractInstance(BaseAddress):
    """
    An interactive instance of a smart contract.
    After you deploy a contract using the :class:`~ape.api.accounts.AccountAPI.deploy` method,
    you get back a contract instance.

    Usage example::

        from ape import accounts, project

        a = accounts.load("alias")  # Load an account by alias
        contract = a.deploy(project.MyContract)  # The result of 'deploy()' is a ContractInstance
    """

    def __init__(
        self,
        address: Union[AddressType, str],
        contract_type: ContractType,
        txn_hash: Optional[str] = None,
    ) -> None:
        super().__init__()
        self._address = address
        self.contract_type = contract_type
        self.txn_hash = txn_hash
        self._cached_receipt: Optional[ReceiptAPI] = None

    @classmethod
    def from_receipt(cls, receipt: ReceiptAPI, contract_type: ContractType) -> "ContractInstance":
        address = receipt.contract_address
        if not address:
            raise ContractError(
                "Receipt missing 'contract_address' field. "
                "Was this from a deploy transaction (e.g. `project.MyContract.deploy()`)?"
            )

        instance = cls(
            address=address,
            contract_type=contract_type,
            txn_hash=receipt.txn_hash,
        )
        instance._cached_receipt = receipt
        return instance

    @property
    def receipt(self) -> Optional[ReceiptAPI]:
        """
        The receipt associated with deploying the contract instance,
        if it is known and exists.
        """

        if not self._cached_receipt and self.txn_hash:
            receipt = self.provider.get_transaction(self.txn_hash)
            self._cached_receipt = receipt
            return receipt

        elif self._cached_receipt:
            return self._cached_receipt

        return None

    def __repr__(self) -> str:
        contract_name = self.contract_type.name or "Unnamed contract"
        return f"<{contract_name} {self.address}>"

    @property
    def address(self) -> AddressType:
        """
        The address of the contract.

        Returns:
            ``AddressType``
        """

        return self.provider.network.ecosystem.decode_address(self._address)

    @cached_property
    def _view_methods_(self) -> Dict[str, ContractCallHandler]:
        view_methods: Dict[str, List[MethodABI]] = dict()

        for abi in self.contract_type.view_methods:
            if abi.name in view_methods:
                view_methods[abi.name].append(abi)
            else:
                view_methods[abi.name] = [abi]

        try:
            return {
                abi_name: ContractCallHandler(contract=self, abis=abis)
                for abi_name, abis in view_methods.items()
            }
        except Exception as err:
            # NOTE: Must raise AttributeError for __attr__ method or will seg fault
            raise AttributeError(str(err)) from err

    @cached_property
    def _mutable_methods_(self) -> Dict[str, ContractTransactionHandler]:
        mutable_methods: Dict[str, List[MethodABI]] = dict()

        for abi in self.contract_type.mutable_methods:
            if abi.name in mutable_methods:
                mutable_methods[abi.name].append(abi)
            else:
                mutable_methods[abi.name] = [abi]

        try:
            return {
                abi_name: ContractTransactionHandler(contract=self, abis=abis)
                for abi_name, abis in mutable_methods.items()
            }
        except Exception as err:
            # NOTE: Must raise AttributeError for __attr__ method or will seg fault
            raise AttributeError(str(err)) from err

    def get_event_by_signature(self, signature: str) -> ContractEvent:
        """
        Get an event by its signature. Most often, you can use the
        :meth:`~ape.contracts.base.ContractInstance.__getattr__`
        method on this class to access events. However, in the case
        when you have more than one event with the same name, such
        as the case where one event is coming from a base contract,
        you can use this method to access the respective events.

        Args:
            signature (str): The signature of the event.

        Returns:
            :class:`~ape.contracts.base.ContractEvent`
        """

        name_from_sig = signature.split("(")[0].strip()
        options = self._events_.get(name_from_sig, [])
        err = ContractError(f"No event found with signature '{signature}'.")
        if not options:
            raise err

        for evt in options:
            if evt.abi.signature == signature:
                return evt

        raise err

    @cached_property
    def _events_(self) -> Dict[str, List[ContractEvent]]:
        events: Dict[str, List[EventABI]] = {}

        for abi in self.contract_type.events:
            if abi.name in events:
                events[abi.name].append(abi)
            else:
                events[abi.name] = [abi]

        try:
            return {
                abi_name: [ContractEvent(contract=self, abi=abi) for abi in abi_list]
                for abi_name, abi_list in events.items()
            }
        except Exception as err:
            # NOTE: Must raise AttributeError for __attr__ method or will seg fault
            raise AttributeError(str(err)) from err

    def __dir__(self) -> List[str]:
        """
        Display methods to IPython on ``c.[TAB]`` tab completion.

        Returns:
            List[str]
        """
        return list(
            set(super(BaseAddress, self).__dir__()).union(
                self._view_methods_, self._mutable_methods_, self._events_
            )
        )

    def __getattr__(self, attr_name: str) -> Any:
        """
        Access a method, property, or event on the contract using ``.`` access.

        Usage example::

            result = contract.vote()  # Implies a method named "vote" exists on the contract.

        Args:
            attr_name (str): The name of the method or property to access.

        Returns:
            Any: The return value from the contract call, or a transaction receipt.
        """

        handler: Union[ContractEvent, ContractCallHandler, ContractTransactionHandler]
        if attr_name in set(super(BaseAddress, self).__dir__()):
            return super(BaseAddress, self).__getattribute__(attr_name)

        if attr_name not in {*self._view_methods_, *self._mutable_methods_, *self._events_}:
            # Didn't find anything that matches
            # NOTE: `__getattr__` *must* raise `AttributeError`
            name = self.contract_type.name or self.__class__.__name__
            raise AttributeError(f"'{name}' has no attribute '{attr_name}'.")

        elif (
            int(attr_name in self._view_methods_)
            + int(attr_name in self._mutable_methods_)
            + int(attr_name in self._events_)
            > 1
        ):
            # ABI should not contain a mix of events, mutable and view methods that match
            # NOTE: `__getattr__` *must* raise `AttributeError`
            raise AttributeError(f"{self.__class__.__name__} has corrupted ABI.")

        if attr_name in self._view_methods_:
            handler = self._view_methods_[attr_name]

        elif attr_name in self._mutable_methods_:
            handler = self._mutable_methods_[attr_name]

        else:
            handler_options = self._events_[attr_name]
            if len(handler_options) > 1:
                raise AttributeError(
                    f"Multiple events named '{attr_name}' in '{self.contract_type.name}'.\n"
                    f"Use 'events_by_signature' look-up."
                )
            handler = handler_options[0]

        return handler


class ContractContainer(ManagerAccessMixin):
    """
    A wrapper around the contract type that has access to the provider.
    When you import your contracts from the :class:`ape.managers.project.ProjectManager`, you
    are using this class.

    Usage example::

        from ape import project

        contract_container = project.MyContract  # Assuming there is a contract named "MyContract"
    """

    def __init__(self, contract_type: ContractType) -> None:
        self.contract_type = contract_type

    def __repr__(self) -> str:
        return f"<{self.contract_type.name}>"

    @property
    def deployments(self):
        """
        Contract deployments.

        Usage example::

            # Get the latest deployment
            my_contract = project.MyContract.deployments[-1]
        """

        return self.chain_manager.contracts.get_deployments(self)

    def at(self, address: AddressType, txn_hash: Optional[str] = None) -> ContractInstance:
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
            txn_hash (str): The hash of the transaction that deployed the contract, if
              available. Defaults to ``None``.

        Returns:
            :class:`~ape.contracts.ContractInstance`
        """

        return self.chain_manager.contracts.instance_at(
            address, self.contract_type, txn_hash=txn_hash
        )

    def __call__(self, *args, **kwargs) -> TransactionAPI:
        args = self.conversion_manager.convert(args, tuple)
        constructor = ContractConstructor(  # type: ignore
            abi=self.contract_type.constructor,
            deployment_bytecode=self.contract_type.get_deployment_bytecode() or b"",  # type: ignore
        )

        args_length = len(args)
        inputs_length = (
            len(constructor.abi.inputs) if constructor.abi and constructor.abi.inputs else 0
        )
        if inputs_length != args_length:
            raise ArgumentsLengthError(args_length, inputs_length=inputs_length)

        return constructor.serialize_transaction(*args, **kwargs)

    def deploy(self, *args, **kwargs) -> ContractInstance:
        txn = self(*args, **kwargs)

        if "sender" in kwargs and isinstance(kwargs["sender"], AccountAPI):
            # Handle account-related preparation if needed, such as signing
            receipt = kwargs["sender"].call(txn)

        else:
            txn = self.provider.prepare_transaction(txn)
            receipt = self.provider.send_transaction(txn)

        if not receipt.contract_address:
            raise ContractError(f"'{receipt.txn_hash}' did not create a contract.")

        styled_address = click.style(receipt.contract_address, bold=True)
        contract_name = self.contract_type.name or "<Unnamed Contract>"
        logger.success(f"Contract '{contract_name}' deployed to: {styled_address}")
        instance = ContractInstance.from_receipt(receipt, self.contract_type)
        self.chain_manager.contracts.cache_deployment(instance)
        return instance


def _get_non_contract_error(address: str, network_name: str) -> ContractError:
    raise ContractError(
        f"Unable to make contract call. "
        f"'{address}' is not a contract on network '{network_name}'."
    )


class ContractNamespace:
    """
    A class that bridges contract containers in a namespace.
    For example, if you have an interface structure like this::

        contracts:
          accounts:
            - interface.json
          mocks:
            - interface.json

    You can interact with them like this::

        account_interface = project.accounts.interface
        mock_interface = project.mocks.interface

    """

    def __init__(self, name: str, contracts: List[ContractContainer]):
        self.name = name
        self.contracts = contracts

    def __repr__(self) -> str:
        return f"<{self.name}>"

    def __getattr__(self, item: str) -> Union[ContractContainer, "ContractNamespace"]:
        """
        Access the next contract container or namespace.

        Args:
            item (str): The name of the next node.

        Returns:
            Union[:class:`~ape.contracts.base.ContractContainer`,
            :class:`~ape.contracts.base.ContractNamespace`]
        """

        def _get_name(cc: ContractContainer) -> str:
            return cc.contract_type.name or ""

        for contract in self.contracts:
            search_contract_name = _get_name(contract)
            search_name = (
                search_contract_name.replace(f"{self.name}.", "") if search_contract_name else None
            )
            if not search_name:
                continue

            elif search_name == item:
                return contract

            elif "." in search_name:
                next_node = search_name.split(".")[0]
                if next_node != item:
                    continue

                subname = f"{self.name}.{next_node}"
                subcontracts = [c for c in self.contracts if _get_name(c).startswith(subname)]
                return ContractNamespace(subname, subcontracts)

        return self.__getattribute__(item)  # type: ignore
