from typing import TYPE_CHECKING, Any, Dict, Iterator, List, Optional, Tuple, Union

import click
from ethpm_types import ContractType
from ethpm_types.abi import ConstructorABI, EventABI, MethodABI
from hexbytes import HexBytes

from ape.api import AccountAPI, Address, ReceiptAPI, TransactionAPI
from ape.api.address import BaseAddress
from ape.exceptions import ArgumentsLengthError, ContractError, ProviderNotConnectedError
from ape.logging import logger
from ape.types import AddressType, ContractLog
from ape.utils import ManagerAccessMixin, cached_property, singledispatchmethod

if TYPE_CHECKING:
    from ape.managers.converters import ConversionManager
    from ape.managers.networks import NetworkManager


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

    def _convert_tuple(self, v: tuple) -> tuple:
        return self.conversion_manager.convert(v, tuple)

    def serialize_transaction(self, *args, **kwargs) -> TransactionAPI:
        args = self._convert_tuple(args)
        kwargs = {
            k: v
            for k, v in zip(
                kwargs.keys(),
                self._convert_tuple(tuple(kwargs.values())),
            )
        }
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

    def _convert_tuple(self, v: tuple) -> tuple:
        return self.conversion_manager.convert(v, tuple)

    def serialize_transaction(self, *args, **kwargs) -> TransactionAPI:
        kwargs = {
            k: v
            for k, v in zip(
                kwargs.keys(),
                self._convert_tuple(tuple(kwargs.values())),
            )
        }
        return self.provider.network.ecosystem.encode_transaction(
            self.address, self.abi, *args, **kwargs
        )

    def __call__(self, *args, **kwargs) -> Any:
        txn = self.serialize_transaction(*args, **kwargs)
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


class ContractCallHandler(ManagerAccessMixin):

    contract: "ContractInstance"
    abis: List[MethodABI]

    def __init__(self, contract: "ContractInstance", abis: List[MethodABI]) -> None:
        super().__init__()
        self.contract = contract
        self.abis = abis

    def __repr__(self) -> str:
        abis = sorted(self.abis, key=lambda abi: len(abi.values or []))  # type: ignore
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

    def _convert_tuple(self, v: tuple) -> tuple:
        return self.conversion_manager.convert(v, tuple)

    def serialize_transaction(self, *args, **kwargs) -> TransactionAPI:
        kwargs = {
            k: v
            for k, v in zip(
                kwargs.keys(),
                self._convert_tuple(tuple(kwargs.values())),
            )
        }
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
        abis = sorted(self.abis, key=lambda abi: len(abi.values or []))  # type: ignore
        return abis[-1].signature

    def _convert_tuple(self, v: tuple) -> tuple:
        return self.conversion_manager.convert(v, tuple)

    def __call__(self, *args, **kwargs) -> ReceiptAPI:
        if not self.contract.is_contract:
            network = self.provider.network.name
            raise _get_non_contract_error(self.contract.address, network)

        args = self._convert_tuple(args)
        selected_abi = _select_method_abi(self.abis, args)

        return ContractTransaction(  # type: ignore
            abi=selected_abi,
            address=self.contract.address,
        )(*args, **kwargs)


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

        if index == 0:
            logs_slice = [next(self._get_logs_iter())]
        elif index > 0:
            # Call over to 'self.__getitem_slice'.
            logs_slice = self[: index + 1]  # type: ignore
        else:
            # Call over to 'self.__getitem_slice'.
            logs_slice = self[index:]  # type: ignore

        try:
            return logs_slice[index]
        except IndexError as err:
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

        start = value.start or 0
        stop = value.stop if value.stop is not None else self.chain_manager.blocks.height
        step = value.step or 1
        collected_logs: List[ContractLog] = []
        counter = 0
        for log in self._get_logs_iter():
            if counter < start:
                counter += 1
                continue

            elif counter >= stop:
                return collected_logs

            elif counter >= start:
                collected_logs.append(log)
                counter += step

        return collected_logs

    def range(
        self,
        start_or_stop: int,
        stop: Optional[int] = None,
        block_page_size: Optional[int] = None,
        event_parameters: Optional[Dict] = None,
    ) -> Iterator[ContractLog]:
        """
        Search through the logs for this event using the given filter parameters.

        Args:
            start_or_stop (int): When also given ``stop``, this is the the
              earliest block number in the desired log set.
              Otherwise, it is the total amount of blocks to get starting from ``0``.
            stop (Optional[int]): The latest block number in the
              desired log set. Defaults to delegating to provider.
            block_page_size (Optional[int]): The amount of block to request
              on each page.
            event_parameters (Optional[Dict]): Arguments on the event that you can
              search for.

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
        yield from self.provider.get_contract_logs(
            self.contract.address,
            self.abi,
            start_block=start_block,
            stop_block=stop_block,
            block_page_size=block_page_size,
            event_parameters=event_parameters,
        )

    def from_receipt(self, receipt: ReceiptAPI) -> Iterator[ContractLog]:
        """
        Get all the events from the given receipt.

        Args:
            receipt (:class:`~ape.api.providers.ReceiptAPI`): The receipt containing the logs.

        Returns:
            Iterator[:class:`~ape.contracts.base.ContractLog`]
        """

        ecosystem = self.provider.network.ecosystem
        yield from ecosystem.decode_logs(self.abi, receipt.logs)

    def _get_logs_iter(self, start_block: int = 0, stop_block: int = None) -> Iterator[ContractLog]:
        stop_block = stop_block or self.chain_manager.blocks.height
        yield from self.provider.get_contract_logs(
            self.contract.address,
            self.abi,
            start_block=start_block,
            stop_block=stop_block,
        )

    def poll_logs(
        self,
        start_block: Optional[int] = None,
        stop_block: Optional[int] = None,
        required_confirmations: Optional[int] = None,
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

        Returns:
            Iterator[:class:`~ape.types.ContractLog`]
        """

        required_confirmations = (
            required_confirmations or self.provider.network.required_confirmations
        )
        stop_block = (
            self.chain_manager.blocks.height if stop_block is None else stop_block
        ) - required_confirmations

        for new_block in self.chain_manager.blocks.poll_blocks(
            start=start_block, stop=stop_block, required_confirmations=required_confirmations
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

    def __init__(self, address: AddressType, contract_type: ContractType) -> None:
        super().__init__()
        self._address = address
        self._contract_type = contract_type

    def __repr__(self) -> str:
        contract_name = self._contract_type.name or "Unnamed contract"
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

        for abi in self._contract_type.view_methods:
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

        for abi in self._contract_type.mutable_methods:
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

    @cached_property
    def _events_(self) -> Dict[str, ContractEvent]:
        events: Dict[str, EventABI] = {}

        for abi in self._contract_type.events:
            if abi.name in events:
                raise ContractError(
                    f"Multiple events with the same ABI defined in '{self._contract_type.name}'."
                )

            events[abi.name] = abi

        try:
            return {
                abi_name: ContractEvent(contract=self, abi=abi) for abi_name, abi in events.items()
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

        if attr_name in set(super(BaseAddress, self).__dir__()):
            return super(BaseAddress, self).__getattribute__(attr_name)

        if attr_name not in {*self._view_methods_, *self._mutable_methods_, *self._events_}:
            # Didn't find anything that matches
            # NOTE: `__getattr__` *must* raise `AttributeError`
            name = self._contract_type.name or self.__class__.__name__
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
            handler = self._mutable_methods_[attr_name]  # type: ignore

        else:
            handler = self._events_[attr_name]  # type: ignore

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

        return self.create_contract(
            address=address,  # type: ignore
            contract_type=self.contract_type,
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

        address = click.style(receipt.contract_address, bold=True)
        contract_name = self.contract_type.name or "<Unnamed Contract>"
        logger.success(f"Contract '{contract_name}' deployed to: {address}")

        return ContractInstance(
            address=receipt.contract_address,  # type: ignore
            contract_type=self.contract_type,
        )


def _Contract(
    address: Union[str, BaseAddress, AddressType],
    networks: "NetworkManager",
    conversion_manager: "ConversionManager",
    contract_type: Optional[ContractType] = None,
) -> BaseAddress:
    """
    Function used to triage whether we have a contract type available for
    the given address/network combo, or explicitly provided. If none are found,
    returns a simple ``Address`` instance instead of throwing (provides a warning)
    """
    provider = networks.active_provider
    if not provider:
        raise ProviderNotConnectedError()

    converted_address: AddressType = conversion_manager.convert(address, AddressType)

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
            address=converted_address,
            contract_type=contract_type,
        )

    else:
        # We don't have a contract type from any source, provide raw address instead
        logger.warning(f"No contract type found for {address}")
        return Address(converted_address)


def _get_non_contract_error(address: str, network_name: str) -> ContractError:
    raise ContractError(
        f"Unable to make contract call. "
        f"'{address}' is not a contract on network '{network_name}'."
    )
