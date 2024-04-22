import re
from ast import literal_eval
from functools import cached_property
from re import Pattern
from typing import Any, Dict, Iterator, Optional, cast

from eth.exceptions import HeaderNotFound
from eth_pydantic_types import HexBytes
from eth_tester.backends import PyEVMBackend  # type: ignore
from eth_tester.exceptions import TransactionFailed  # type: ignore
from eth_utils import is_0x_prefixed
from eth_utils.exceptions import ValidationError
from eth_utils.toolz import merge
from web3 import EthereumTesterProvider, Web3
from web3.exceptions import ContractPanicError
from web3.providers.eth_tester.defaults import API_ENDPOINTS, static_return
from web3.types import TxParams

from ape.api import PluginConfig, ReceiptAPI, TestProviderAPI, TransactionAPI
from ape.exceptions import (
    ContractLogicError,
    ProviderError,
    ProviderNotConnectedError,
    TransactionError,
    UnknownSnapshotError,
    VirtualMachineError,
)
from ape.types import BlockID, ContractLog, LogFilter, SnapshotID
from ape.utils import DEFAULT_TEST_CHAIN_ID, DEFAULT_TEST_HD_PATH, gas_estimation_error_message
from ape_ethereum.provider import Web3Provider


class EthTesterProviderConfig(PluginConfig):
    chain_id: int = DEFAULT_TEST_CHAIN_ID
    auto_mine: bool = True


class LocalProvider(TestProviderAPI, Web3Provider):
    _evm_backend: Optional[PyEVMBackend] = None
    _CANNOT_AFFORD_GAS_PATTERN: Pattern = re.compile(
        r"Sender b'[\\*|\w]*' cannot afford txn gas (\d+) with account balance (\d+)"
    )
    _INVALID_NONCE_PATTERN: Pattern = re.compile(
        r"Invalid transaction nonce: Expected (\d+), but got (\d+)"
    )

    @property
    def evm_backend(self) -> PyEVMBackend:
        if self._evm_backend is None:
            raise ProviderNotConnectedError()

        return self._evm_backend

    @cached_property
    def tester(self):
        chain_id = self.settings.chain_id
        if self._web3 is not None:
            connected_chain_id = self._make_request("eth_chainId")
            if connected_chain_id == chain_id:
                # Is already connected and settings have not changed.
                return

        hd_path = (self.config.hd_path or DEFAULT_TEST_HD_PATH).rstrip("/")
        self._evm_backend = PyEVMBackend.from_mnemonic(
            mnemonic=self.config.mnemonic,
            num_accounts=self.config.number_of_accounts,
            hd_path=hd_path,
        )
        endpoints = {**API_ENDPOINTS}
        endpoints["eth"] = merge(endpoints["eth"], {"chainId": static_return(chain_id)})
        return EthereumTesterProvider(ethereum_tester=self._evm_backend, api_endpoints=endpoints)

    @property
    def auto_mine(self) -> bool:
        return self.tester.ethereum_tester.auto_mine_transactions

    @auto_mine.setter
    def auto_mine(self, value: Any) -> None:
        if value is True:
            self.tester.ethereum_tester.enable_auto_mine_transactions()
        elif value is False:
            self.tester.ethereum_tester.disable_auto_mine_transactions()
        else:
            raise TypeError("Expecting bool-value for auto_mine setter.")

    def connect(self):
        if "tester" in self.__dict__:
            del self.__dict__["tester"]

        self._web3 = Web3(self.tester)
        # Handle disabling auto-mine if the user requested via config.
        if self.config.provider.auto_mine is False:
            self.auto_mine = False  # type: ignore[misc]

    def disconnect(self):
        # NOTE: This type ignore seems like a bug in pydantic.
        self._web3 = None
        self._evm_backend = None
        self.provider_settings = {}

    def update_settings(self, new_settings: Dict):
        self.provider_settings = {**self.provider_settings, **new_settings}
        self.disconnect()
        self.connect()

    def estimate_gas_cost(
        self, txn: TransactionAPI, block_id: Optional[BlockID] = None, **kwargs
    ) -> int:
        if isinstance(self.network.gas_limit, int):
            return self.network.gas_limit

        estimate_gas = self.web3.eth.estimate_gas

        # NOTE: Using JSON mode since used as request data.
        txn_dict = txn.model_dump(mode="json")

        txn_dict.pop("gas", None)
        txn_data = cast(TxParams, txn_dict)

        try:
            return estimate_gas(txn_data, block_identifier=block_id)
        except (ValidationError, TransactionFailed) as err:
            ape_err = self.get_virtual_machine_error(err, txn=txn)
            gas_match = self._INVALID_NONCE_PATTERN.match(str(ape_err))
            if gas_match:
                # Sometimes, EthTester is confused about the sender nonce
                # during gas estimation. Retry using the "expected" gas
                # and then set it back.
                expected_nonce, actual_nonce = gas_match.groups()
                txn.nonce = int(expected_nonce)

                # NOTE: Using JSON mode since used as request data.
                txn_params: TxParams = cast(TxParams, txn.model_dump(by_alias=True, mode="json"))

                value = estimate_gas(txn_params, block_identifier=block_id)
                txn.nonce = int(actual_nonce)
                return value

            elif isinstance(ape_err, ContractLogicError):
                raise ape_err from err
            else:
                message = gas_estimation_error_message(ape_err)
                raise TransactionError(
                    message, base_err=ape_err, txn=txn, source_traceback=ape_err.source_traceback
                ) from ape_err

    @property
    def settings(self) -> EthTesterProviderConfig:
        return EthTesterProviderConfig.model_validate(
            {**self.config.provider.model_dump(), **self.provider_settings}
        )

    @cached_property
    def chain_id(self) -> int:
        try:
            result = self._make_request("eth_chainId")
        except ProviderNotConnectedError:
            result = self.settings.chain_id

        return result

    @property
    def gas_price(self) -> int:
        return self.base_fee  # no miner tip

    @property
    def priority_fee(self) -> int:
        """Returns 0 because test chains do not care about priority fees."""
        return 0

    @property
    def base_fee(self) -> int:
        """
        EthTester does not implement RPC `eth_feeHistory`.
        Returns the last base fee on chain.
        """
        return self._get_last_base_fee()

    def send_call(
        self,
        txn: TransactionAPI,
        block_id: Optional[BlockID] = None,
        state: Optional[Dict] = None,
        **kwargs,
    ) -> HexBytes:
        # NOTE: Using JSON mode since used as request data.
        data = txn.model_dump(mode="json", exclude_none=True)

        state = kwargs.pop("state_override", None)
        call_kwargs: Dict = {"block_identifier": block_id, "state_override": state}

        # Remove unneeded properties
        data.pop("gas", None)
        data.pop("gasLimit", None)
        data.pop("maxFeePerGas", None)
        data.pop("maxPriorityFeePerGas", None)

        tx_params = cast(TxParams, data)

        try:
            result = self.web3.eth.call(tx_params, **call_kwargs)
        except ValidationError as err:
            raise VirtualMachineError(base_err=err) from err
        except (TransactionFailed, ContractPanicError) as err:
            raise self.get_virtual_machine_error(err, txn=txn) from err

        self._increment_call_func_coverage_hit_count(txn)
        return HexBytes(result)

    def send_transaction(self, txn: TransactionAPI) -> ReceiptAPI:
        try:
            txn_hash = self.web3.eth.send_raw_transaction(txn.serialize_transaction())
        except (ValidationError, TransactionFailed) as err:
            vm_err = self.get_virtual_machine_error(err, txn=txn)
            raise vm_err from err

        receipt = self.get_receipt(
            txn_hash.hex(), required_confirmations=txn.required_confirmations or 0
        )

        # NOTE: Caching must happen before error enrichment.
        self.chain_manager.history.append(receipt)

        if receipt.failed:
            # NOTE: Using JSON mode since used as request data.
            txn_dict = txn.model_dump(mode="json")

            txn_dict["nonce"] += 1
            txn_params = cast(TxParams, txn_dict)

            # Replay txn to get revert reason
            try:
                self.web3.eth.call(txn_params)
            except (ValidationError, TransactionFailed) as err:
                vm_err = self.get_virtual_machine_error(err, txn=receipt)
                raise vm_err from err

            # If we get here, for some reason the tx-replay did not produce
            # a VM error.
            receipt.raise_for_status()

        return receipt

    def snapshot(self) -> SnapshotID:
        return self.evm_backend.take_snapshot()

    def revert(self, snapshot_id: SnapshotID):
        if snapshot_id:
            current_hash = self.get_block("latest").hash
            if current_hash != snapshot_id:
                try:
                    return self.evm_backend.revert_to_snapshot(snapshot_id)
                except HeaderNotFound:
                    raise UnknownSnapshotError(snapshot_id)

    def set_timestamp(self, new_timestamp: int):
        current = self.get_block("pending").timestamp
        if new_timestamp == current:
            # Is the same, treat as a noop.
            return

        try:
            self.evm_backend.time_travel(new_timestamp)
        except ValidationError as err:
            pattern = re.compile(
                r"timestamp must be strictly later than parent, "
                r"but is 0 seconds before\.\n- child\s{2}: (\d*)\n- parent : (\d*)\.\s*"
            )
            if match := re.match(pattern, str(err)):
                if groups := match.groups():
                    if groups[0].strip() == groups[1].strip():
                        # Handle race condition when block headers are the same.
                        # Treat as noop, same as pre-check.
                        return

            raise ProviderError(f"Failed to time travel: {err}") from err

    def mine(self, num_blocks: int = 1):
        self.evm_backend.mine_blocks(num_blocks)

    def get_contract_logs(self, log_filter: LogFilter) -> Iterator[ContractLog]:
        from_block = max(0, log_filter.start_block)

        if log_filter.stop_block is None:
            to_block = None
        else:
            latest_block = self.get_block("latest").number
            to_block = (
                min(latest_block, log_filter.stop_block)
                if latest_block is not None
                else log_filter.stop_block
            )

        log_gen = self.tester.ethereum_tester.get_logs(
            address=log_filter.addresses,
            from_block=from_block,
            to_block=to_block,
            topics=log_filter.topic_filter,
        )
        yield from self.network.ecosystem.decode_logs(log_gen, *log_filter.events)

    def get_virtual_machine_error(self, exception: Exception, **kwargs) -> VirtualMachineError:
        if isinstance(exception, ValidationError):
            match = self._CANNOT_AFFORD_GAS_PATTERN.match(str(exception))
            if match:
                txn_gas, bal = match.groups()
                sender = getattr(kwargs["txn"], "sender")
                new_message = (
                    f"Sender '{sender}' cannot afford txn gas {txn_gas} with account balance {bal}."
                )
                return VirtualMachineError(new_message, base_err=exception, **kwargs)

            else:
                return VirtualMachineError(base_err=exception, **kwargs)

        elif isinstance(exception, ContractPanicError):
            # If the ape-solidity plugin is installed, we are able to enrich the data.
            message = exception.message
            raw_data = exception.data if isinstance(exception.data, str) else "0x"
            error = ContractLogicError(base_err=exception, revert_message=raw_data, **kwargs)
            enriched_error = self.compiler_manager.enrich_error(error)
            if is_0x_prefixed(enriched_error.message):
                # Failed to enrich. Use nicer message from web3.py.
                enriched_error.message = message or enriched_error.message

            return enriched_error

        elif isinstance(exception, TransactionFailed):
            err_message = str(exception).split("execution reverted: ")[-1] or None

            if err_message and err_message.startswith("b'") and err_message.endswith("'"):
                # Convert stringified bytes str like `"b'\\x82\\xb4)\\x00'"` to `"0x82b42900"`.
                # (Notice the `b'` is within the `"` on the first str).
                err_message = HexBytes(literal_eval(err_message)).hex()

            err_message = TransactionError.DEFAULT_MESSAGE if err_message == "0x" else err_message
            contract_err = ContractLogicError(
                base_err=exception, revert_message=err_message, **kwargs
            )
            return self.compiler_manager.enrich_error(contract_err)

        else:
            return VirtualMachineError(base_err=exception, **kwargs)
