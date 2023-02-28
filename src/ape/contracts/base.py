from functools import partial
from itertools import islice
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional, Tuple, Union

import click
import pandas as pd
from ethpm_types import ContractType
from ethpm_types.abi import ConstructorABI, EventABI, MethodABI
from hexbytes import HexBytes

from ape.api import AccountAPI, Address, ReceiptAPI, TransactionAPI
from ape.api.address import BaseAddress
from ape.api.query import ContractEventQuery, extract_fields
from ape.exceptions import ArgumentsLengthError, ChainError, ContractError, TransactionNotFoundError
from ape.logging import logger
from ape.types import AddressType, ContractLog, LogFilter
from ape.utils import ManagerAccessMixin, cached_property, singledispatchmethod


def _convert_args(arguments, converter, abi) -> Tuple:
    input_types = [i.canonical_type for i in abi.inputs]
    pre_processed_args = []
    for ipt, argument in zip(input_types, arguments):
        # Handle primitive-addresses separately since they may not occur
        # on the tuple-conversion if they are integers or bytes.
        if str(ipt) == "address":
            converted_value = converter(argument, AddressType)
            pre_processed_args.append(converted_value)
        else:
            pre_processed_args.append(argument)

    return converter(pre_processed_args, tuple)


def _convert_kwargs(kwargs, converter) -> Dict:
    fields = TransactionAPI.__fields__
    kwargs_to_convert = {k: v for k, v in kwargs.items() if k == "sender" or k in fields}
    converted_fields = {
        k: converter(v, AddressType if k == "sender" else fields[k].type_)
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

    def encode_input(self, *args) -> HexBytes:
        ecosystem = self.provider.network.ecosystem
        encoded_calldata = ecosystem.encode_calldata(self.abi, *args)
        return HexBytes(encoded_calldata)

    def decode_input(self, calldata: bytes) -> Tuple[str, Dict[str, Any]]:
        decoded_inputs = self.provider.network.ecosystem.decode_calldata(self.abi, calldata)
        return self.abi.selector, decoded_inputs

    def serialize_transaction(self, *args, **kwargs) -> TransactionAPI:
        arguments = _convert_args(args, self.conversion_manager.convert, self.abi)
        kwargs = _convert_kwargs(kwargs, self.conversion_manager.convert)
        return self.provider.network.ecosystem.encode_deployment(
            self.deployment_bytecode, self.abi, *arguments, **kwargs
        )

    def __call__(self, *args, **kwargs) -> ReceiptAPI:
        txn = self.serialize_transaction(*args, **kwargs)

        if "sender" in kwargs and isinstance(kwargs["sender"], AccountAPI):
            sender = kwargs["sender"]
            return sender.call(txn, **kwargs)
        elif "sender" not in kwargs and self.account_manager.default_sender is not None:
            return self.account_manager.default_sender.call(txn, **kwargs)

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


class ContractMethodHandler(ManagerAccessMixin):

    contract: "ContractInstance"
    abis: List[MethodABI]

    def __init__(self, contract: "ContractInstance", abis: List[MethodABI]) -> None:
        super().__init__()
        self.contract = contract
        self.abis = abis

    def __repr__(self) -> str:
        abis = sorted(self.abis, key=lambda abi: len(abi.inputs or []))
        return abis[-1].signature

    def encode_input(self, *args) -> HexBytes:
        selected_abi = _select_method_abi(self.abis, args)
        args = self._convert_tuple(args, selected_abi)
        ecosystem = self.provider.network.ecosystem
        encoded_calldata = ecosystem.encode_calldata(selected_abi, *args)
        method_id = ecosystem.get_method_selector(selected_abi)
        return HexBytes(method_id + encoded_calldata)

    def decode_input(self, calldata: bytes) -> Tuple[str, Dict[str, Any]]:
        matching_abis = []
        err = ContractError(
            f"Unable to find matching method ABI for calldata '{calldata.hex()}'. "
            "Try prepending a method ID to the beginning of the calldata."
        )
        for abi in self.abis:
            selector = self.provider.network.ecosystem.get_method_selector(abi)
            if calldata.startswith(selector):
                cutoff = len(selector)
                rest_calldata = calldata[cutoff:]
                matching_abis.append(abi)

        if len(matching_abis) == 1:
            abi = matching_abis[0]
            decoded_input = self.provider.network.ecosystem.decode_calldata(
                matching_abis[0], HexBytes(rest_calldata)
            )
            return abi.selector, decoded_input

        elif len(matching_abis) > 1:
            raise err

        # Brute-force find method ABI
        valid_results = []
        for abi in self.abis:
            decoded_calldata = {}
            try:
                decoded_calldata = self.provider.network.ecosystem.decode_calldata(
                    abi, HexBytes(calldata)
                )
            except Exception:
                continue

            if decoded_calldata:
                valid_results.append((abi, decoded_calldata))

        if len(valid_results) == 1:
            selected_abi, decoded_calldata = valid_results[0]
            return selected_abi.selector, decoded_calldata

        raise err

    def _convert_tuple(self, v: tuple, abi) -> tuple:
        return _convert_args(v, self.conversion_manager.convert, abi)


class ContractCallHandler(ContractMethodHandler):
    def __call__(self, *args, **kwargs) -> Any:
        if not self.contract.is_contract:
            network = self.provider.network.name
            raise _get_non_contract_error(self.contract.address, network)

        selected_abi = _select_method_abi(self.abis, args)
        args = self._convert_tuple(args, selected_abi)

        return ContractCall(
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

        selected_abi = _select_method_abi(self.abis, args)
        arguments = _convert_args(args, self.conversion_manager.convert, selected_abi)
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
        if "sender" in kwargs and isinstance(kwargs["sender"], (ContractInstance, Address)):
            # Automatically impersonate contracts (if API available) when sender
            kwargs["sender"] = self.account_manager.test_accounts[kwargs["sender"].address]

        arguments = _convert_args(args, self.conversion_manager.convert, self.abi)
        kwargs = _convert_kwargs(kwargs, self.conversion_manager.convert)
        return self.provider.network.ecosystem.encode_transaction(
            self.address, self.abi, *arguments, **kwargs
        )

    def __call__(self, *args, **kwargs) -> ReceiptAPI:
        txn = self.serialize_transaction(*args, **kwargs)

        if "sender" in kwargs and isinstance(kwargs["sender"], AccountAPI):
            return kwargs["sender"].call(txn, **kwargs)

        return self.provider.send_transaction(txn)


class ContractTransactionHandler(ContractMethodHandler):
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
        selected_abi = _select_method_abi(self.abis, args)
        arguments = _convert_args(args, self.conversion_manager.convert, selected_abi)
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

    def __call__(self, *args, **kwargs) -> ReceiptAPI:
        contract_transaction = self._as_transaction(*args)
        if "sender" not in kwargs and self.account_manager.default_sender is not None:
            kwargs["sender"] = self.account_manager.default_sender

        return contract_transaction(*args, **kwargs)

    def _as_transaction(self, *args) -> ContractTransaction:
        if not self.contract.is_contract:
            network = self.provider.network.name
            raise _get_non_contract_error(self.contract.address, network)

        selected_abi = _select_method_abi(self.abis, args)
        args = self._convert_tuple(args, selected_abi)

        return ContractTransaction(
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
        cached_logs: Optional[List[ContractLog]] = None,
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
        data = map(partial(extract_fields, columns=columns), contract_events)
        return pd.DataFrame(columns=columns, data=data)

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

    def from_receipt(self, receipt: ReceiptAPI) -> List[ContractLog]:
        """
        Get all the events from the given receipt.

        Args:
            receipt (:class:`~ape.api.transactions.ReceiptAPI`): The receipt containing the logs.

        Returns:
            List[:class:`~ape.contracts.base.ContractLog`]
        """
        ecosystem = self.provider.network.ecosystem

        # NOTE: Safe to use a list because a receipt should never have too many logs.
        return list(ecosystem.decode_logs(receipt.logs, self.abi))

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

            for new_log in contract.MyEvent.poll_logs():
                print(f"New event log found: block_number={new_log.block_number}")

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


class ContractTypeWrapper(ManagerAccessMixin):
    contract_type: ContractType

    def decode_input(self, calldata: bytes) -> Tuple[str, Dict[str, Any]]:
        """
        Decode the given calldata using this contract.
        If the calldata has a method ID prefix, Ape will detect it and find
        the corresponding method, else it will error.

        Args:
            calldata (bytes): The calldata to decode.

        Returns:
            Tuple[str, Dict[str, Any]]: A tuple containing the method selector
            along a mapping of input names to their decoded values.
            If an input does not have a number, it will have the stringified
            index as its key.
        """

        ecosystem = self.provider.network.ecosystem
        if calldata in self.contract_type.mutable_methods:
            method = self.contract_type.mutable_methods[calldata]
        elif calldata in self.contract_type.view_methods:
            method = self.contract_type.view_methods[calldata]
        else:
            method = None

        if not method:
            raise ContractError(
                f"Unable to find method ABI from calldata '{calldata.hex()}'. "
                "Try prepending the method ID to the beginning of the calldata."
            )

        method_id = ecosystem.get_method_selector(method)
        cutoff = len(method_id)
        rest_calldata = calldata[cutoff:]
        input_dict = ecosystem.decode_calldata(method, rest_calldata)
        return method.selector, input_dict


class ContractInstance(BaseAddress, ContractTypeWrapper):
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
        address: AddressType,
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

            try:
                receipt = self.chain_manager.get_receipt(self.txn_hash)
            except TransactionNotFoundError:
                return None

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

        return self._address

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

    def call_view_method(self, method_name: str, *args, **kwargs) -> Any:
        """
        Call a contract's view function directly using the method_name.
        This is helpful in the scenario where the contract has a
        method name matching an attribute of the
        :class:`~ape.api.address.BaseAddress` class, such as ``nonce``
        or ``balance``

        Args:
            method_name (str): The contract method name to be called
            *args: Contract method arguments.
            **kwargs: Transaction values, such as ``value`` or ``sender``

        Returns:
            Any: Output of smart contract view call.

        """

        if method_name in self._view_methods_:
            view_handler = self._view_methods_[method_name]
            output = view_handler(*args, **kwargs)
            return output

        elif method_name in self._mutable_methods_:
            handler = self._mutable_methods_[method_name].call
            output = handler(*args, **kwargs)
            return output

        else:
            # Didn't find anything that matches
            name = self.contract_type.name or self.__class__.__name__
            raise AttributeError(f"'{name}' has no attribute '{method_name}'.")

    def invoke_transaction(self, method_name: str, *args, **kwargs) -> ReceiptAPI:
        """
        Call a contract's function directly using the method_name.
        This function is for non-view function's which may change
        contract state and will execute a transaction.
        This is helpful in the scenario where the contract has a
        method name matching an attribute of the
        :class:`~ape.api.address.BaseAddress` class, such as ``nonce``
        or ``balance``

        Args:
            method_name (str): The contract method name to be called
            *args: Contract method arguments.
            **kwargs: Transaction values, such as ``value`` or ``sender``

        Returns:
            :class:`~ape.api.transactions.ReceiptAPI`: Output of smart contract interaction.

        """

        if method_name in self._view_methods_:
            view_handler = self._view_methods_[method_name].transact
            output = view_handler(*args, **kwargs)
            return output

        elif method_name in self._mutable_methods_:
            handler = self._mutable_methods_[method_name]
            output = handler(*args, **kwargs)
            return output

        else:
            # Didn't find anything that matches
            name = self.contract_type.name or self.__class__.__name__
            raise AttributeError(f"'{name}' has no attribute '{method_name}'.")

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

        # NOTE: Type ignores because of this issue: https://github.com/python/typing/issues/1112
        #  They can be removed after next `mypy` release containing fix.
        values = [
            "contract_type",
            "txn_hash",
            ContractInstance.receipt.fget.__name__,  # type: ignore[attr-defined]
        ]
        return list(
            set(self._base_dir_values).union(
                self._view_methods_, self._mutable_methods_, self._events_, values
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
            return self._view_methods_[attr_name]

        elif attr_name in self._mutable_methods_:
            return self._mutable_methods_[attr_name]

        elif attr_name in self._events_:
            handler_options = self._events_[attr_name]
            if len(handler_options) > 1:
                raise AttributeError(
                    f"Multiple events named '{attr_name}' in '{self.contract_type.name}'.\n"
                    f"Use '{self.get_event_by_signature.__name__}' look-up."
                )

            return handler_options[0]

        else:
            raise AttributeError(f"No attribute '{attr_name}' found in contract '{self.address}'.")


class ContractContainer(ContractTypeWrapper):
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

    @cached_property
    def source_path(self) -> Optional[Path]:
        """
        Returns the path to the local contract if determined that this container
        belongs to the active project by cross checking source_id.

        WARN: The will return a path if the contract has the same
        source ID as one in the current project. That does not necessarily mean
        they are the same contract, however.
        """
        contract_name = self.contract_type.name
        source_id = self.contract_type.source_id
        if not (contract_name and source_id):
            return None

        contract_container = self.project_manager._get_contract(contract_name)
        if not (
            contract_container
            and contract_container.contract_type.source_id
            and self.contract_type.source_id
        ):
            return None

        if source_id == contract_container.contract_type.source_id:
            return self.project_manager.contracts_folder / source_id
        else:
            return None

    @cached_property
    def constructor(self) -> ContractConstructor:
        return ContractConstructor(
            abi=self.contract_type.constructor,
            deployment_bytecode=self.contract_type.get_deployment_bytecode() or HexBytes(""),
        )

    def __call__(self, *args, **kwargs) -> TransactionAPI:
        args_length = len(args)
        inputs_length = (
            len(self.constructor.abi.inputs)
            if self.constructor.abi and self.constructor.abi.inputs
            else 0
        )
        if inputs_length != args_length:
            raise ArgumentsLengthError(args_length, inputs_length=inputs_length)

        return self.constructor.serialize_transaction(*args, **kwargs)

    def deploy(self, *args, publish: bool = False, **kwargs) -> ContractInstance:
        txn = self(*args, **kwargs)

        if "sender" in kwargs and isinstance(kwargs["sender"], AccountAPI):
            # Handle account-related preparation if needed, such as signing
            receipt = kwargs["sender"].call(txn, **kwargs)

        else:
            txn = self.provider.prepare_transaction(txn)
            receipt = self.provider.send_transaction(txn)

        address = receipt.contract_address
        if not address:
            raise ContractError(f"'{receipt.txn_hash}' did not create a contract.")

        styled_address = click.style(receipt.contract_address, bold=True)
        contract_name = self.contract_type.name or "<Unnamed Contract>"
        logger.success(f"Contract '{contract_name}' deployed to: {styled_address}")
        instance = ContractInstance.from_receipt(receipt, self.contract_type)
        self.chain_manager.contracts.cache_deployment(instance)

        if publish:
            self.project_manager.track_deployment(instance)
            self.provider.network.publish_contract(address)

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

        return self.__getattribute__(item)
