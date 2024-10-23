import json
import os
import re
import sys
import time
from abc import ABC
from collections.abc import Iterable, Iterator
from concurrent.futures import ThreadPoolExecutor
from copy import copy
from functools import cached_property, wraps
from pathlib import Path
from typing import Any, Optional, Union, cast

import ijson  # type: ignore
import requests
from eth_pydantic_types import HexBytes
from eth_typing import BlockNumber, HexStr
from eth_utils import add_0x_prefix, is_hex, to_hex
from ethpm_types import EventABI
from evmchains import get_random_rpc
from pydantic.dataclasses import dataclass
from requests import HTTPError
from web3 import HTTPProvider, IPCProvider, Web3
from web3 import WebsocketProvider as WebSocketProvider
from web3._utils.http import construct_user_agent
from web3.exceptions import ContractLogicError as Web3ContractLogicError
from web3.exceptions import (
    ExtraDataLengthError,
    MethodUnavailable,
    TimeExhausted,
    TransactionNotFound,
)
from web3.gas_strategies.rpc import rpc_gas_price_strategy
from web3.middleware import geth_poa_middleware as ExtraDataToPOAMiddleware
from web3.middleware.validation import MAX_EXTRADATA_LENGTH
from web3.providers import AutoProvider
from web3.providers.auto import load_provider_from_environment
from web3.types import FeeHistory, RPCEndpoint, TxParams

from ape.api.address import Address
from ape.api.providers import BlockAPI, ProviderAPI
from ape.api.trace import TraceAPI
from ape.api.transactions import ReceiptAPI, TransactionAPI
from ape.exceptions import (
    ApeException,
    APINotImplementedError,
    BlockNotFoundError,
    ConfigError,
    ContractLogicError,
    ContractNotFoundError,
    OutOfGasError,
    ProviderError,
    ProviderNotConnectedError,
    TransactionError,
    TransactionNotFoundError,
    VirtualMachineError,
)
from ape.logging import logger, sanitize_url
from ape.types.address import AddressType
from ape.types.events import ContractLog, LogFilter
from ape.types.gas import AutoGasLimit
from ape.types.trace import SourceTraceback
from ape.types.vm import BlockID, ContractCode
from ape.utils.basemodel import ManagerAccessMixin
from ape.utils.misc import DEFAULT_MAX_RETRIES_TX, gas_estimation_error_message, to_int
from ape_ethereum._print import CONSOLE_ADDRESS, console_contract
from ape_ethereum.trace import CallTrace, TraceApproach, TransactionTrace
from ape_ethereum.transactions import AccessList, AccessListTransaction, TransactionStatusEnum

DEFAULT_PORT = 8545
DEFAULT_HOSTNAME = "localhost"
DEFAULT_SETTINGS = {"uri": f"http://{DEFAULT_HOSTNAME}:{DEFAULT_PORT}"}


def _sanitize_web3_url(msg: str) -> str:
    """Sanitize RPC URI from given log string"""

    # `auto` used by some providers to figure it out automatically
    if "URI: " not in msg or "URI: auto" in msg:
        return msg

    parts = msg.split("URI: ")
    prefix = parts[0].strip()
    rest = parts[1].split(" ")

    # * To remove the `,` from the url http://127.0.0.1:8545,
    if "," in rest[0]:
        rest[0] = rest[0].rstrip(",")
    sanitized_url = sanitize_url(rest[0])
    return f"{prefix} URI: {sanitized_url} {' '.join(rest[1:])}"


WEB3_PROVIDER_URI_ENV_VAR_NAME = "WEB3_PROVIDER_URI"


def assert_web3_provider_uri_env_var_not_set():
    """
    Environment variable $WEB3_PROVIDER_URI causes problems
    when used with Ape (ignores Ape's networks). Use
    this validator to eliminate the concern.

    Raises:
          :class:`~ape.exceptions.ProviderError`: If environment variable
            WEB3_PROVIDER_URI exists in ``os.environ``.
    """
    if WEB3_PROVIDER_URI_ENV_VAR_NAME not in os.environ:
        return

    # NOTE: This was the source of confusion for user when they noticed
    #  Ape would only connect to RPC URL set by an environment variable
    #  named $WEB3_PROVIDER_URI instead of whatever network they were telling Ape.
    raise ProviderError(
        "Ape does not support Web3.py's environment variable "
        f"${WEB3_PROVIDER_URI_ENV_VAR_NAME}. If you are using this environment "
        "variable name incidentally, please use a different name. If you are "
        "trying to set the network in Web3.py, please use Ape's `ape-config.yaml` "
        "or `--network` option instead."
    )


class Web3Provider(ProviderAPI, ABC):
    """
    A base provider mixin class that uses the
    `web3.py <https://web3py.readthedocs.io/en/stable/>`__ python package.
    """

    _web3: Optional[Web3] = None
    _client_version: Optional[str] = None

    _call_trace_approach: Optional[TraceApproach] = None
    """
    Is ``None`` until known.
    NOTE: This gets set in `ape_ethereum.trace.Trace`.
    """

    _supports_debug_trace_call: Optional[bool] = None

    _transaction_trace_cache: dict[str, TransactionTrace] = {}

    def __new__(cls, *args, **kwargs):
        assert_web3_provider_uri_env_var_not_set()

        # Post-connection ops
        def post_connect_hook(connect):
            @wraps(connect)
            def connect_wrapper(self):
                connect(self)
                self._post_connect()

            return connect_wrapper

        # Patching the provider to call a post send_transaction() hook
        def post_tx_hook(send_tx):
            @wraps(send_tx)
            def send_tx_wrapper(self, txn: TransactionAPI) -> ReceiptAPI:
                receipt = send_tx(self, txn)
                self._post_send_transaction(txn, receipt)
                return receipt

            return send_tx_wrapper

        setattr(cls, "send_transaction", post_tx_hook(cls.send_transaction))
        setattr(cls, "connect", post_connect_hook(cls.connect))
        return super().__new__(cls)  # pydantic v2 doesn't want args

    def __init__(self, *args, **kwargs):
        logger.create_logger("web3.RequestManager", handlers=(_sanitize_web3_url,))
        logger.create_logger("web3.providers.HTTPProvider", handlers=(_sanitize_web3_url,))
        super().__init__(*args, **kwargs)

    @property
    def web3(self) -> Web3:
        """
        Access to the ``web3`` object as if you did ``Web3(HTTPProvider(uri))``.
        """

        if web3 := self._web3:
            return web3

        raise ProviderNotConnectedError()

    @property
    def http_uri(self) -> Optional[str]:
        """
        The connected HTTP URI. If using providers
        like `ape-node`, configure your URI and that will
        be returned here instead.
        """
        try:
            web3 = self.web3
        except ProviderNotConnectedError:
            if uri := getattr(self, "uri", None):
                if _is_http_url(uri):
                    return uri

            return None

        if (
            hasattr(web3.provider, "endpoint_uri")
            and isinstance(web3.provider.endpoint_uri, str)
            and web3.provider.endpoint_uri.startswith("http")
        ):
            return web3.provider.endpoint_uri

        if uri := getattr(self, "uri", None):
            if _is_http_url(uri):
                return uri

        return None

    @property
    def ws_uri(self) -> Optional[str]:
        try:
            web3 = self.web3
        except ProviderNotConnectedError:
            return None

        if (
            hasattr(web3.provider, "endpoint_uri")
            and isinstance(web3.provider.endpoint_uri, str)
            and web3.provider.endpoint_uri.startswith("ws")
        ):
            return web3.provider.endpoint_uri

        return None

    @property
    def client_version(self) -> str:
        if not self._web3:
            return ""

        # NOTE: Gets reset to `None` on `connect()` and `disconnect()`.
        if self._client_version is None:
            self._client_version = self.web3.client_version

        return self._client_version

    @property
    def base_fee(self) -> int:
        latest_block_number = self._get_latest_block_rpc().get("number")
        if latest_block_number is None:
            # Possibly no blocks yet.
            logger.debug("Latest block has no number. Using base fee of '0'.")
            return 0

        try:
            fee_history = self._get_fee_history(latest_block_number)
        except Exception as exc:
            # Use the less-accurate approach (OK for testing).
            logger.debug(
                "Failed using `web3.eth.fee_history` for network "
                f"'{self.network_choice}'. Error: {exc}"
            )
            return self._get_last_base_fee()

        if "baseFeePerGas" not in fee_history or len(fee_history["baseFeePerGas"] or []) < 2:
            logger.debug("Not enough fee_history. Defaulting less-accurate approach.")
            return self._get_last_base_fee()

        pending_base_fee = fee_history["baseFeePerGas"][1]
        if pending_base_fee is None:
            # Non-EIP-1559 chains or we time-travelled pre-London fork.
            return self._get_last_base_fee()

        return to_int(pending_base_fee)

    @property
    def call_trace_approach(self) -> Optional[TraceApproach]:
        """
        The default tracing approach to use when building up a call-tree.
        By default, Ape attempts to use the faster approach. Meaning, if
        geth-call-tracer or parity are available, Ape will use one of those
        instead of building a call-trace entirely from struct-logs.
        """
        if approach := self._call_trace_approach:
            return approach

        return self.settings.get("call_trace_approach")

    def _get_fee_history(self, block_number: int) -> FeeHistory:
        try:
            return self.web3.eth.fee_history(1, BlockNumber(block_number), reward_percentiles=[])
        except (MethodUnavailable, AttributeError) as err:
            raise APINotImplementedError(str(err)) from err

    def _get_last_base_fee(self) -> int:
        base_fee = self._get_latest_block_rpc().get("baseFeePerGas", None)
        if base_fee is not None:
            return to_int(base_fee)

        raise APINotImplementedError("No base fee found in block.")

    @property
    def is_connected(self) -> bool:
        if self._web3 is None:
            return False

        return self._web3.is_connected()

    @property
    def max_gas(self) -> int:
        return int(self._get_latest_block_rpc()["gasLimit"], 16)

    @cached_property
    def supports_tracing(self) -> bool:
        try:
            # NOTE: Txn hash is purposely not a real hash.
            self.make_request("debug_traceTransaction", ["__CHECK_IF_SUPPORTS_TRACING__"])
        except NotImplementedError:
            return False

        except Exception:
            # We know tracing works because we didn't get a NotImplementedError.
            return True

        return True

    def update_settings(self, new_settings: dict):
        self.disconnect()
        self.provider_settings.update(new_settings)
        self.connect()

    def estimate_gas_cost(self, txn: TransactionAPI, block_id: Optional[BlockID] = None) -> int:
        # NOTE: Using JSON mode since used as request data.
        txn_dict = txn.model_dump(by_alias=True, mode="json")

        # Force the use of hex values to support a wider range of nodes.
        if isinstance(txn_dict.get("type"), int):
            txn_dict["type"] = to_hex(txn_dict["type"])

        # NOTE: "auto" means to enter this method, so remove it from dict
        if "gas" in txn_dict and (
            txn_dict["gas"] == "auto" or isinstance(txn_dict["gas"], AutoGasLimit)
        ):
            txn_dict.pop("gas")
            # Also pop these, they are overridden by "auto"
            txn_dict.pop("maxFeePerGas", None)
            txn_dict.pop("maxPriorityFeePerGas", None)

        txn_params = cast(TxParams, txn_dict)
        try:
            return self.web3.eth.estimate_gas(txn_params, block_identifier=block_id)
        except (ValueError, Web3ContractLogicError) as err:
            # NOTE: Try to use debug_traceCall to obtain a trace.
            #  And the RPC can be very picky with inputs.
            tx_to_trace: dict = {}
            for key, val in txn_params.items():
                if isinstance(val, int):
                    tx_to_trace[key] = hex(val)
                else:
                    tx_to_trace[key] = val

            tx_error = self.get_virtual_machine_error(
                err,
                txn=txn,
                trace=lambda: CallTrace(tx=txn),
                set_ape_traceback=False,
            )

            # If this is the cause of a would-be revert,
            # raise ContractLogicError so that we can confirm tx-reverts.
            if isinstance(tx_error, ContractLogicError):
                raise tx_error from err

            message = gas_estimation_error_message(tx_error)
            raise TransactionError(
                message,
                base_err=tx_error,
                txn=txn,
                source_traceback=lambda: tx_error.source_traceback,
                set_ape_traceback=True,
            ) from err

    @cached_property
    def chain_id(self) -> int:
        default_chain_id = None
        if self.network.name != "custom" and not self.network.is_dev:
            # If using a live network, the chain ID is hardcoded.
            default_chain_id = self.network.chain_id

        try:
            if hasattr(self.web3, "eth"):
                return self.web3.eth.chain_id

        except ProviderNotConnectedError:
            if default_chain_id is not None:
                return default_chain_id

            raise  # Original error

        if default_chain_id is not None:
            return default_chain_id

        raise ProviderNotConnectedError()

    @property
    def gas_price(self) -> int:
        price = self.web3.eth.generate_gas_price() or 0
        return to_int(price)

    @property
    def priority_fee(self) -> int:
        try:
            return self.web3.eth.max_priority_fee
        except MethodUnavailable as err:
            # The user likely should be using a more-catered plugin.
            raise APINotImplementedError(
                "eth_maxPriorityFeePerGas not supported in this RPC. Please specify manually."
            ) from err

    def get_block(self, block_id: BlockID) -> BlockAPI:
        if isinstance(block_id, str) and block_id.isnumeric():
            block_id = int(block_id)

        try:
            block_data = dict(self.web3.eth.get_block(block_id))
        except Exception as err:
            raise BlockNotFoundError(block_id, reason=str(err)) from err

        return self.network.ecosystem.decode_block(block_data)

    def _get_latest_block(self) -> BlockAPI:
        # perf: By-pass as much as possible since this is a common action.
        data = self._get_latest_block_rpc()
        return self.network.ecosystem.decode_block(data)

    def _get_latest_block_rpc(self) -> dict:
        return self.make_request("eth_getBlockByNumber", ["latest", False])

    def get_nonce(self, address: AddressType, block_id: Optional[BlockID] = None) -> int:
        return self.web3.eth.get_transaction_count(address, block_identifier=block_id)

    def get_balance(self, address: AddressType, block_id: Optional[BlockID] = None) -> int:
        return self.web3.eth.get_balance(address, block_identifier=block_id)

    def get_code(self, address: AddressType, block_id: Optional[BlockID] = None) -> ContractCode:
        return self.web3.eth.get_code(address, block_identifier=block_id)

    def get_storage(
        self, address: AddressType, slot: int, block_id: Optional[BlockID] = None
    ) -> HexBytes:
        try:
            return HexBytes(self.web3.eth.get_storage_at(address, slot, block_identifier=block_id))
        except ValueError as err:
            if "RPC Endpoint has not been implemented" in str(err):
                raise APINotImplementedError(str(err)) from err

            raise  # Raise original error

    def get_transaction_trace(self, transaction_hash: str, **kwargs) -> TraceAPI:
        if transaction_hash in self._transaction_trace_cache:
            return self._transaction_trace_cache[transaction_hash]

        if "call_trace_approach" not in kwargs:
            kwargs["call_trace_approach"] = self.call_trace_approach

        trace = TransactionTrace(transaction_hash=transaction_hash, **kwargs)
        self._transaction_trace_cache[transaction_hash] = trace
        return trace

    def send_call(
        self,
        txn: TransactionAPI,
        block_id: Optional[BlockID] = None,
        state: Optional[dict] = None,
        **kwargs: Any,
    ) -> HexBytes:
        if block_id is not None:
            kwargs["block_identifier"] = block_id

        if state is not None:
            kwargs["state_override"] = state

        raise_on_revert = kwargs.get("raise_on_revert", txn.raise_on_revert)
        skip_trace = kwargs.pop("skip_trace", False)
        arguments = self._prepare_call(txn, **kwargs)
        if skip_trace:
            return self._eth_call(
                arguments, raise_on_revert=txn.raise_on_revert, skip_trace=skip_trace
            )

        show_gas = kwargs.pop("show_gas_report", False)
        show_trace = kwargs.pop("show_trace", False)

        if self._test_runner is not None:
            track_gas = self._test_runner.gas_tracker.enabled
            track_coverage = self._test_runner.coverage_tracker.enabled
        else:
            track_gas = False
            track_coverage = False

        needs_trace = track_gas or track_coverage or show_gas or show_trace
        if not needs_trace:
            return self._eth_call(arguments, raise_on_revert=raise_on_revert, skip_trace=skip_trace)

        # The user is requesting information related to a call's trace,
        # such as gas usage data.

        # When looking at gas, we cannot use token symbols in enrichment.
        # Else, the table is difficult to understand.
        use_symbol_for_tokens = track_gas or show_gas

        trace = CallTrace(
            tx=arguments[0],
            arguments=arguments[1:],
            use_symbol_for_tokens=use_symbol_for_tokens,
            supports_debug_trace_call=self._supports_debug_trace_call,
        )

        if track_gas and self._test_runner is not None and txn.receiver:
            self._test_runner.gas_tracker.append_gas(trace, txn.receiver)

        if track_coverage and self._test_runner is not None and txn.receiver:
            if contract_type := self.chain_manager.contracts.get(txn.receiver):
                if contract_src := self.local_project._create_contract_source(contract_type):
                    method_id = HexBytes(txn.data)
                    selector = (
                        contract_type.methods[method_id].selector
                        if method_id in contract_type.methods
                        else None
                    )
                    source_traceback = SourceTraceback.create(contract_src, trace, method_id)
                    self._test_runner.coverage_tracker.cover(
                        source_traceback, function=selector, contract=contract_type.name
                    )

        if show_gas:
            trace.show_gas_report()

        if show_trace:
            trace.show()

        return HexBytes(trace.return_value)

    def _eth_call(
        self, arguments: list, raise_on_revert: bool = True, skip_trace: bool = False
    ) -> HexBytes:
        # Force the usage of hex-type to support a wider-range of nodes.
        txn_dict = copy(arguments[0])
        if isinstance(txn_dict.get("type"), int):
            txn_dict["type"] = to_hex(txn_dict["type"])

        # Remove unnecessary values to support a wider-range of nodes.
        txn_dict.pop("chainId", None)

        arguments[0] = txn_dict
        try:
            result = self.make_request("eth_call", arguments)
        except Exception as err:
            contract_address = arguments[0].get("to")
            _lazy_call_trace = _LazyCallTrace(arguments)

            if not skip_trace:
                if address := contract_address:
                    try:
                        contract_type = self.chain_manager.contracts.get(address)
                    except RecursionError:
                        # Occurs when already in the middle of fetching this contract.
                        pass
                    else:
                        _lazy_call_trace.contract_type = contract_type

            vm_err = self.get_virtual_machine_error(
                err,
                trace=lambda: _lazy_call_trace.trace,
                contract_address=contract_address,
                source_traceback=lambda: _lazy_call_trace.source_traceback,
                set_ape_traceback=raise_on_revert,
            )
            if raise_on_revert:
                raise vm_err.with_ape_traceback() from err

            else:
                logger.error(vm_err)
                result = "0x"

        if "error" in result:
            raise ProviderError(result["error"]["message"])

        return HexBytes(result)

    def _prepare_call(self, txn: Union[dict, TransactionAPI], **kwargs) -> list:
        # NOTE: Using mode="json" because used in request data.
        txn_dict = (
            txn.model_dump(by_alias=True, mode="json") if isinstance(txn, TransactionAPI) else txn
        )
        fields_to_convert = ("data", "chainId", "value")
        for field in fields_to_convert:
            value = txn_dict.get(field)
            if value is not None and not isinstance(value, str):
                txn_dict[field] = to_hex(value)

        # Remove unneeded properties
        txn_dict.pop("gas", None)
        txn_dict.pop("gasLimit", None)
        txn_dict.pop("maxFeePerGas", None)
        txn_dict.pop("maxPriorityFeePerGas", None)
        txn_dict.pop("signature", None)

        # NOTE: Block ID is required so if given None, default to `"latest"`.
        block_identifier = kwargs.pop("block_identifier", kwargs.pop("block_id", None)) or "latest"
        if isinstance(block_identifier, int):
            block_identifier = to_hex(primitive=block_identifier)

        arguments = [txn_dict, block_identifier]
        if "state_override" in kwargs:
            arguments.append(kwargs["state_override"])

        return arguments

    def get_receipt(
        self,
        txn_hash: str,
        required_confirmations: int = 0,
        timeout: Optional[int] = None,
        **kwargs,
    ) -> ReceiptAPI:
        if required_confirmations < 0:
            raise TransactionError("Required confirmations cannot be negative.")

        timeout = (
            timeout if timeout is not None else self.provider.network.transaction_acceptance_timeout
        )
        hex_hash = HexBytes(txn_hash)

        txn: dict = {}
        if transaction := kwargs.get("transaction"):
            # perf: If called `send_transaction()`, we should already have the data!
            txn = (
                transaction
                if isinstance(transaction, dict)
                else transaction.model_dump(by_alias=True, mode="json")
            )

        private = kwargs.get("private")

        try:
            receipt_data = dict(
                self.web3.eth.wait_for_transaction_receipt(hex_hash, timeout=timeout)
            )
        except TimeExhausted as err:
            # Since private transactions can take longer,
            #  return a partial receipt instead of throwing a TimeExhausted error.
            if private:
                # Return with a partial receipt
                data = {
                    "block_number": -1,
                    "required_confirmations": required_confirmations,
                    "txn_hash": txn_hash,
                    "status": TransactionStatusEnum.NO_ERROR,
                    **txn,
                }
                receipt = self._create_receipt(**data)
                return receipt
            msg_str = str(err)
            if f"HexBytes('{txn_hash}')" in msg_str:
                msg_str = msg_str.replace(f"HexBytes('{txn_hash}')", f"'{txn_hash}'")

            raise TransactionNotFoundError(
                transaction_hash=txn_hash, error_message=msg_str
            ) from err

        ecosystem_config = self.network.ecosystem_config
        network_config: dict = ecosystem_config.get(self.network.name, {})
        max_retries = network_config.get("max_get_transaction_retries", DEFAULT_MAX_RETRIES_TX)

        if transaction:
            if "effectiveGasPrice" in receipt_data:
                receipt_data["gasPrice"] = receipt_data["effectiveGasPrice"]

        else:
            for attempt in range(max_retries):
                try:
                    txn = dict(self.web3.eth.get_transaction(HexStr(txn_hash)))
                    break

                except TransactionNotFound:
                    if attempt < max_retries - 1:
                        # Not the last attempt. Wait and then retry.
                        time.sleep(0.5)
                        continue

                    else:
                        # It was the last attempt - raise the exception as-is.
                        raise

        data = {"required_confirmations": required_confirmations, **txn, **receipt_data}
        receipt = self._create_receipt(**data)
        return receipt.await_confirmations()

    def _create_receipt(self, **kwargs) -> ReceiptAPI:
        data = {"provider": self, **kwargs}
        return self.network.ecosystem.decode_receipt(data)

    def get_transactions_by_block(self, block_id: BlockID) -> Iterator[TransactionAPI]:
        if isinstance(block_id, str):
            block_id = HexStr(block_id)

            if block_id.isnumeric():
                block_id = add_0x_prefix(block_id)

        block = cast(dict, self.web3.eth.get_block(block_id, full_transactions=True))
        for transaction in block.get("transactions", []):
            yield self.network.ecosystem.create_transaction(**transaction)

    def get_transactions_by_account_nonce(
        self,
        account: AddressType,
        start_nonce: int = 0,
        stop_nonce: int = -1,
    ) -> Iterator[ReceiptAPI]:
        if start_nonce > stop_nonce:
            raise ValueError("Starting nonce cannot be greater than stop nonce for search")

        if not self.network.is_local and (stop_nonce - start_nonce) > 2:
            # NOTE: RPC usage might be acceptable to find 1 or 2 transactions reasonably quickly
            logger.warning(
                "Performing this action is likely to be very slow and may "
                f"use {20 * (stop_nonce - start_nonce)} or more RPC calls. "
                "Consider installing an alternative data query provider plugin."
            )

        yield from self._find_txn_by_account_and_nonce(
            account,
            start_nonce,
            stop_nonce,
            0,  # first block
            self.chain_manager.blocks.head.number or 0,  # last block (or 0 if genesis-only chain)
        )

    def _find_txn_by_account_and_nonce(
        self,
        account: AddressType,
        start_nonce: int,
        stop_nonce: int,
        start_block: int,
        stop_block: int,
    ) -> Iterator[ReceiptAPI]:
        # binary search between `start_block` and `stop_block` to yield txns from account,
        # ordered from `start_nonce` to `stop_nonce`

        if start_block == stop_block:
            # Honed in on one block where there's a delta in nonce, so must be the right block
            for txn in self.get_transactions_by_block(stop_block):
                assert isinstance(txn.nonce, int)  # NOTE: just satisfying mypy here
                if txn.sender == account and txn.nonce >= start_nonce:
                    yield self.get_receipt(to_hex(txn.txn_hash))

            # Nothing else to search for

        else:
            # Break up into smaller chunks
            # NOTE: biased to `stop_block`
            block_number = start_block + (stop_block - start_block) // 2 + 1
            txn_count_prev_to_block = self.web3.eth.get_transaction_count(account, block_number - 1)

            if start_nonce < txn_count_prev_to_block:
                yield from self._find_txn_by_account_and_nonce(
                    account,
                    start_nonce,
                    min(txn_count_prev_to_block - 1, stop_nonce),  # NOTE: In case >1 txn in block
                    start_block,
                    block_number - 1,
                )

            if txn_count_prev_to_block <= stop_nonce:
                yield from self._find_txn_by_account_and_nonce(
                    account,
                    max(start_nonce, txn_count_prev_to_block),  # NOTE: In case >1 txn in block
                    stop_nonce,
                    block_number,
                    stop_block,
                )

    def poll_blocks(
        self,
        stop_block: Optional[int] = None,
        required_confirmations: Optional[int] = None,
        new_block_timeout: Optional[int] = None,
    ) -> Iterator[BlockAPI]:
        # Wait half the time as the block time
        # to get data faster.
        block_time = self.network.block_time
        wait_time = block_time / 2

        # The timeout occurs when there is no chain activity
        # after a certain time.
        timeout = (
            (10.0 if self.network.is_dev else 50 * block_time)
            if new_block_timeout is None
            else new_block_timeout
        )

        # Only yield confirmed blocks.
        if required_confirmations is None:
            required_confirmations = self.network.required_confirmations

        @dataclass
        class YieldAction:
            hash: bytes
            number: int
            time: float

        # Pretend we _did_ yield the last confirmed item, for logic's sake.
        fake_last_block = self.get_block(self.web3.eth.block_number - required_confirmations)
        last_num = fake_last_block.number or 0
        last_hash = fake_last_block.hash or HexBytes(0)
        last: YieldAction = YieldAction(number=last_num, hash=last_hash, time=time.time())

        # A helper method for various points of ensuring we didn't timeout.
        def assert_chain_activity():
            time_waiting = time.time() - last.time
            if time_waiting > timeout:
                raise ProviderError("Timed out waiting for next block.")

        # Begin the daemon.
        while True:
            # The next block we want is simply 1 after the last.
            next_block = last.number + 1
            head = self._get_latest_block()
            try:
                if head.number is None or head.hash is None:
                    raise ProviderError("Head block has no number or hash.")
                # Use an "adjusted" head, based on the required confirmations.
                adjusted_head = self.get_block(head.number - required_confirmations)
                if adjusted_head.number is None or adjusted_head.hash is None:
                    raise ProviderError("Adjusted head block has no number or hash.")
            except Exception:
                # TODO: I did encounter this sometimes in a re-org, needs better handling
                # and maybe bubbling up the block number/hash exceptions above.
                assert_chain_activity()
                continue

            if adjusted_head.number == last.number and adjusted_head.hash == last.hash:
                # The chain has not moved! Verify we have activity.
                assert_chain_activity()
                time.sleep(wait_time)
                continue

            elif adjusted_head.number < last.number or (
                adjusted_head.number == last.number and adjusted_head.hash != last.hash
            ):
                # Re-org detected! Error and catch up the chain.
                logger.error(
                    "Chain has reorganized since returning the last block. "
                    "Try adjusting the required network confirmations."
                )
                # Catch up the chain by setting the "next" to this tiny head.
                next_block = adjusted_head.number

                # NOTE: Drop down to code outside of switch-of-ifs

            elif adjusted_head.number < next_block:
                # Wait for the next block.
                # But first, let's make sure the chain is still active.
                assert_chain_activity()
                time.sleep(wait_time)
                continue

            # NOTE: Should only get here if yielding blocks!
            #  Either because it is finally time or because a re-org allows us.
            for block_idx in range(next_block, adjusted_head.number + 1):
                block = self.get_block(block_idx)
                if block.number is None or block.hash is None:
                    raise ProviderError("Block has no number or hash.")
                yield block

                # This is the point at which the daemon will end,
                # provider the user passes in a `stop_block` arg.
                if stop_block is not None and block.number >= stop_block:
                    return

                # Set the last action, used for checking timeouts and re-orgs.
                last = YieldAction(number=block.number, hash=block.hash, time=time.time())

    def poll_logs(
        self,
        stop_block: Optional[int] = None,
        address: Optional[AddressType] = None,
        topics: Optional[list[Union[str, list[str]]]] = None,
        required_confirmations: Optional[int] = None,
        new_block_timeout: Optional[int] = None,
        events: Optional[list[EventABI]] = None,
    ) -> Iterator[ContractLog]:
        events = events or []
        if required_confirmations is None:
            required_confirmations = self.network.required_confirmations

        if stop_block is not None:
            if stop_block <= (self._get_latest_block().number or 0):
                raise ValueError("'stop' argument must be in the future.")

        for block in self.poll_blocks(stop_block, required_confirmations, new_block_timeout):
            if block.number is None:
                raise ValueError("Block number cannot be None")

            log_params: dict[str, Any] = {
                "start_block": block.number,
                "stop_block": block.number,
                "events": events,
            }
            if address is not None:
                log_params["addresses"] = [address]
            if topics is not None:
                log_params["topics"] = topics

            log_filter = LogFilter(**log_params)
            yield from self.get_contract_logs(log_filter)

    def block_ranges(self, start: int = 0, stop: Optional[int] = None, page: Optional[int] = None):
        if stop is None:
            stop = self.chain_manager.blocks.height
        if page is None:
            page = self.block_page_size

        for start_block in range(start, stop + 1, page):
            stop_block = min(stop, start_block + page - 1)
            yield start_block, stop_block

    def get_contract_logs(self, log_filter: LogFilter) -> Iterator[ContractLog]:
        height = self.chain_manager.blocks.height
        start_block = log_filter.start_block
        stop_block_arg = log_filter.stop_block if log_filter.stop_block is not None else height
        stop_block = min(stop_block_arg, height)
        block_ranges = self.block_ranges(start_block, stop_block, self.block_page_size)

        def fetch_log_page(block_range):
            start, stop = block_range
            update = {"start_block": start, "stop_block": stop}
            page_filter = log_filter.model_copy(update=update)

            # NOTE: Using JSON mode since used as request data.
            filter_params = page_filter.model_dump(mode="json")
            logs = self.make_request("eth_getLogs", [filter_params])
            return self.network.ecosystem.decode_logs(logs, *log_filter.events)

        with ThreadPoolExecutor(self.concurrency) as pool:
            for page in pool.map(fetch_log_page, block_ranges):
                yield from page

    def prepare_transaction(self, txn: TransactionAPI) -> TransactionAPI:
        # NOTE: Use "expected value" for Chain ID, so if it doesn't match actual, we raise
        txn.chain_id = self.network.chain_id

        from ape_ethereum.transactions import StaticFeeTransaction, TransactionType

        txn_type = TransactionType(txn.type)
        if (
            txn_type in (TransactionType.STATIC, TransactionType.ACCESS_LIST)
            and isinstance(txn, StaticFeeTransaction)
            and txn.gas_price is None
        ):
            txn.gas_price = self.gas_price
        elif txn_type in (TransactionType.DYNAMIC, TransactionType.SHARED_BLOB):
            if txn.max_priority_fee is None:
                txn.max_priority_fee = self.priority_fee

            if txn.max_fee is None:
                multiplier = self.network.base_fee_multiplier
                txn.max_fee = int(self.base_fee * multiplier + txn.max_priority_fee)

            # else: Assume user specified the correct amount or txn will fail and waste gas

        if txn_type is TransactionType.ACCESS_LIST and isinstance(txn, AccessListTransaction):
            if not txn.access_list:
                try:
                    txn.access_list = self.create_access_list(txn)
                except APINotImplementedError:
                    pass

        gas_limit = self.network.gas_limit if txn.gas_limit is None else txn.gas_limit
        if gas_limit in (None, "auto") or isinstance(gas_limit, AutoGasLimit):
            multiplier = (
                gas_limit.multiplier
                if isinstance(gas_limit, AutoGasLimit)
                else self.network.auto_gas_multiplier
            )
            if multiplier != 1.0:
                gas = min(int(self.estimate_gas_cost(txn) * multiplier), self.max_gas)
            else:
                gas = self.estimate_gas_cost(txn)

            txn.gas_limit = gas

        elif gas_limit == "max":
            txn.gas_limit = self.max_gas

        elif gas_limit is not None and isinstance(gas_limit, int):
            txn.gas_limit = gas_limit

        if txn.required_confirmations is None:
            txn.required_confirmations = self.network.required_confirmations
        elif not isinstance(txn.required_confirmations, int) or txn.required_confirmations < 0:
            raise TransactionError("'required_confirmations' must be a positive integer.")

        return txn

    def send_transaction(self, txn: TransactionAPI) -> ReceiptAPI:
        vm_err = None
        txn_data = None
        txn_hash = None
        try:
            if txn.sender is not None and txn.signature is None:
                # Missing signature, user likely trying to use an unlocked account.
                attempt_send = True
                if (
                    self.network.is_dev
                    and txn.sender not in self.account_manager.test_accounts._impersonated_accounts
                ):
                    try:
                        self.account_manager.test_accounts.impersonate_account(txn.sender)
                    except NotImplementedError:
                        # Unable to impersonate. Try sending as raw-tx.
                        attempt_send = False

                if attempt_send:
                    # For some reason, some nodes have issues with integer-types.
                    txn_data = {
                        k: to_hex(v) if isinstance(v, int) else v
                        for k, v in txn.model_dump(by_alias=True, mode="json").items()
                    }
                    tx_params = cast(TxParams, txn_data)
                    txn_hash = to_hex(self.web3.eth.send_transaction(tx_params))
                # else: attempt raw tx

            if txn_hash is None:
                txn_hash = to_hex(self.web3.eth.send_raw_transaction(txn.serialize_transaction()))

        except (ValueError, Web3ContractLogicError) as err:
            vm_err = self.get_virtual_machine_error(
                err, txn=txn, set_ape_traceback=txn.raise_on_revert
            )
            if txn.raise_on_revert:
                raise vm_err from err
            else:
                txn_hash = to_hex(txn.txn_hash)

        required_confirmations = (
            txn.required_confirmations
            if txn.required_confirmations is not None
            else self.network.required_confirmations
        )
        txn_data = txn_data or txn.model_dump(by_alias=True, mode="json")
        if vm_err:
            receipt = self._create_receipt(
                block_number=-1,  # Not in a block.
                error=vm_err,
                required_confirmations=required_confirmations,
                status=TransactionStatusEnum.FAILING,
                txn_hash=txn_hash,
                **txn_data,
            )
        else:
            receipt = self.get_receipt(
                txn_hash,
                required_confirmations=required_confirmations,
                transaction=txn_data,
            )

        # NOTE: Ensure to cache even the failed receipts.
        # NOTE: Caching must happen before error enrichment.
        self.chain_manager.history.append(receipt)

        if receipt.failed:
            # For some reason, some nodes have issues with integer-types.
            if isinstance(txn_data.get("type"), int):
                txn_data["type"] = to_hex(txn_data["type"])

            # NOTE: For some reason, some providers have issues with
            #   `nonce`, it's not needed anyway.
            txn_data.pop("nonce", None)

            # NOTE: Using JSON mode since used as request data.
            txn_params = cast(TxParams, txn_data)

            # Replay txn to get revert reason
            try:
                self.web3.eth.call(txn_params)
            except Exception as err:
                vm_err = self.get_virtual_machine_error(
                    err, txn=txn, set_ape_traceback=txn.raise_on_revert
                )
                receipt.error = vm_err
                if txn.raise_on_revert:
                    raise vm_err from err

            if txn.raise_on_revert:
                # If we get here, for some reason the tx-replay did not produce
                # a VM error.
                receipt.raise_for_status()

        if receipt.error:
            logger.error(receipt.error)

        return receipt

    def _post_send_transaction(self, tx: TransactionAPI, receipt: ReceiptAPI):
        """Execute post-transaction ops"""

        # TODO: Optional configuration?
        if tx.receiver and Address(tx.receiver).is_contract:
            # Look for and print any contract logging
            try:
                receipt.show_debug_logs()
            except TransactionNotFound:
                # Receipt never published. Likely failed.
                pass
            except Exception as err:
                # Avoid letting debug logs causes program crashes.
                logger.debug(f"Unable to show debug logs: {err}")

        logger.info(f"Confirmed {receipt.txn_hash} (total fees paid = {receipt.total_fees_paid})")

    def _post_connect(self):
        # Register the console contract for trace enrichment
        self.chain_manager.contracts._cache_contract_type(CONSOLE_ADDRESS, console_contract)

    def make_request(self, rpc: str, parameters: Optional[Iterable] = None) -> Any:
        parameters = parameters or []

        try:
            result = self.web3.provider.make_request(RPCEndpoint(rpc), parameters)
        except HTTPError as err:
            if "method not allowed" in str(err).lower():
                raise APINotImplementedError(
                    f"RPC method '{rpc}' is not implemented by this node instance."
                )

            raise ProviderError(str(err)) from err

        if "error" in result:
            error = result["error"]
            message = (
                error["message"] if isinstance(error, dict) and "message" in error else str(error)
            )

            if (
                "does not exist/is not available" in str(message)
                or re.match(r"[m|M]ethod .*?not found", message)
                or message.startswith("Unknown RPC Endpoint")
                or "RPC Endpoint has not been implemented" in message
            ):
                raise APINotImplementedError(
                    f"RPC method '{rpc}' is not implemented by this node instance."
                )

            raise ProviderError(message)

        elif "result" in result:
            return result.get("result", {})

        return result

    def stream_request(self, method: str, params: Iterable, iter_path: str = "result.item"):
        if not (uri := self.http_uri):
            raise ProviderError("This provider has no HTTP URI and is unable to stream requests.")

        payload = {"jsonrpc": "2.0", "id": 1, "method": method, "params": params}
        results = ijson.sendable_list()
        coroutine = ijson.items_coro(results, iter_path)
        resp = requests.post(uri, json=payload, stream=True)
        resp.raise_for_status()

        for chunk in resp.iter_content(chunk_size=2**17):
            coroutine.send(chunk)
            yield from results
            del results[:]

    def create_access_list(
        self, transaction: TransactionAPI, block_id: Optional[BlockID] = None
    ) -> list[AccessList]:
        """
        Get the access list for a transaction use ``eth_createAccessList``.

        Args:
            transaction (:class:`~ape.api.transactions.TransactionAPI`): The
              transaction to check.
            block_id (:class:`~ape.types.BlockID`): Optionally specify a block
              ID. Defaults to using the latest block.

        Returns:
            list[:class:`~ape_ethereum.transactions.AccessList`]
        """
        # NOTE: Using JSON mode since used in request data.
        tx_dict = transaction.model_dump(by_alias=True, mode="json", exclude={"chain_id"})
        tx_dict_converted = {}
        for key, val in tx_dict.items():
            if isinstance(val, int):
                # This RPC requires hex-str values.
                if val > 0:
                    tx_dict_converted[key] = to_hex(val)
                # else: 0-values cause problems.

            else:
                tx_dict_converted[key] = val

        if not tx_dict_converted.get("to") and tx_dict.get("data") in (None, "0x"):
            # Contract creation with no data, can skip.
            return []

        arguments: list = [tx_dict_converted]
        if block_id is not None:
            arguments.append(block_id)

        result = self.make_request("eth_createAccessList", arguments)
        return [AccessList.model_validate(x) for x in result.get("accessList", [])]

    def get_virtual_machine_error(self, exception: Exception, **kwargs) -> VirtualMachineError:
        txn = kwargs.get("txn")
        if isinstance(exception, Web3ContractLogicError):
            # This happens from `assert` or `require` statements.
            return self._handle_execution_reverted(exception, **kwargs)

        if not len(exception.args):
            return VirtualMachineError(base_err=exception, **kwargs)

        err_data = exception.args[0] if (hasattr(exception, "args") and exception.args) else None
        if isinstance(err_data, str) and "execution reverted" in err_data:
            return self._handle_execution_reverted(exception, **kwargs)

        elif not isinstance(err_data, dict):
            # Maybe it is a JSON-str.
            # NOTE: For some reason, it comes back with single quotes though.
            try:
                err_data = json.loads(str(err_data or "").replace("'", '"'))
            except Exception:
                return VirtualMachineError(base_err=exception, **kwargs)

        if not (err_msg := err_data.get("message")):
            return VirtualMachineError(base_err=exception, **kwargs)

        elif txn is not None and "nonce too low" in str(err_msg):
            txn = cast(TransactionAPI, txn)
            new_err_msg = f"Nonce '{txn.nonce}' is too low"
            return VirtualMachineError(
                new_err_msg, base_err=exception, code=err_data.get("code"), **kwargs
            )

        elif "out of gas" in str(err_msg) or "intrinsic gas too low" in str(err_msg):
            return OutOfGasError(code=err_data.get("code"), base_err=exception, **kwargs)

        return VirtualMachineError(str(err_msg), code=(err_data or {}).get("code"), **kwargs)

    def _handle_execution_reverted(
        self,
        exception: Union[Exception, str],
        txn: Optional[TransactionAPI] = None,
        trace: Optional[TraceAPI] = None,
        contract_address: Optional[AddressType] = None,
        source_traceback: Optional[SourceTraceback] = None,
        set_ape_traceback: Optional[bool] = None,
    ) -> ContractLogicError:
        if hasattr(exception, "args") and len(exception.args) == 2:
            message = exception.args[0].replace("execution reverted: ", "")
            data = exception.args[1]
        else:
            message = str(exception).split(":")[-1].strip()
            data = None

        params: dict = {
            "trace": trace,
            "contract_address": contract_address,
            "source_traceback": source_traceback,
        }
        if set_ape_traceback is not None:
            params["set_ape_traceback"] = set_ape_traceback

        no_reason = message == "execution reverted"

        if isinstance(exception, Web3ContractLogicError) and no_reason:
            # Check for custom exception data and use that as the message instead.
            # This allows compiler exception enrichment to function.
            if data != "no data" and is_hex(data):
                message = add_0x_prefix(data)

            else:
                if trace is None and txn is not None:
                    trace = self.provider.get_transaction_trace(to_hex(txn.txn_hash))

                if trace is not None and (revert_message := trace.revert_message):
                    message = revert_message
                    no_reason = False
                    if revert_message := trace.revert_message:
                        message = revert_message
                        no_reason = False

        result = (
            ContractLogicError(txn=txn, **params)
            if no_reason
            else ContractLogicError(
                base_err=exception if isinstance(exception, Exception) else None,
                revert_message=message,
                txn=txn,
                **params,
            )
        )
        enriched = self.compiler_manager.enrich_error(result)

        # Show call trace if available
        if enriched.txn:
            # Unlikely scenario where a transaction is on the error even though a receipt exists.
            if isinstance(enriched.txn, TransactionAPI) and enriched.txn.receipt:
                enriched.txn.receipt.show_trace()
            elif isinstance(enriched.txn, ReceiptAPI):
                enriched.txn.show_trace()

        return enriched


class EthereumNodeProvider(Web3Provider, ABC):
    # optimal values for geth
    block_page_size: int = 5000
    concurrency: int = 16

    name: str = "node"

    # NOTE: Appends user-agent to base User-Agent string.
    request_header: dict = {
        "User-Agent": construct_user_agent(str(HTTPProvider)),
    }

    @property
    def uri(self) -> str:
        if "url" in self.provider_settings:
            raise ConfigError("Unknown provider setting 'url'. Did you mean 'uri'?")
        elif uri := self.provider_settings.get("uri"):
            if _is_uri(uri):
                return uri
            else:
                raise TypeError(f"Not an URI: {uri}")

        config = self.config.model_dump().get(self.network.ecosystem.name, None)
        if config is None:
            if rpc := self._get_random_rpc():
                return rpc
            elif self.network.is_dev:
                return DEFAULT_SETTINGS["uri"]

            # We have no way of knowing what URL the user wants.
            raise ProviderError(f"Please configure a URL for '{self.network_choice}'.")

        # Use value from config file
        network_config = config.get(self.network.name) or DEFAULT_SETTINGS

        if "url" in network_config:
            raise ConfigError("Unknown provider setting 'url'. Did you mean 'uri'?")
        elif "http_uri" in network_config:
            key = "http_uri"
        elif "uri" in network_config:
            key = "uri"
        elif "ipc_path" in network_config:
            key = "ipc_path"
        elif "ws_uri" in network_config:
            key = "ws_uri"
        elif rpc := self._get_random_rpc():
            return rpc
        else:
            key = "uri"

        settings_uri = network_config.get(key, DEFAULT_SETTINGS["uri"])
        if _is_uri(settings_uri):
            return settings_uri

        # Likely was an IPC Path (or websockets) and will connect that way.
        return super().http_uri or ""

    @property
    def http_uri(self) -> Optional[str]:
        uri = self.uri
        return uri if _is_http_url(uri) else None

    @property
    def ws_uri(self) -> Optional[str]:
        if "ws_uri" in self.provider_settings:
            # Use adhoc, scripted value
            return self.provider_settings["ws_uri"]

        elif "uri" in self.provider_settings and _is_ws_url(self.provider_settings["uri"]):
            return self.provider_settings["uri"]

        config: dict = self.config.get(self.network.ecosystem.name, {})
        if config == {}:
            return super().ws_uri

        # Use value from config file
        network_config = config.get(self.network.name) or DEFAULT_SETTINGS
        if "ws_uri" not in network_config:
            if "uri" in network_config and _is_ws_url(network_config["uri"]):
                return network_config["uri"]

            return super().ws_uri

        settings_uri = network_config.get("ws_uri")
        if settings_uri and _is_ws_url(settings_uri):
            return settings_uri

        return super().ws_uri

    def _get_random_rpc(self) -> Optional[str]:
        if self.network.is_dev:
            return None

        ecosystem = self.network.ecosystem.name
        network = self.network.name

        # Use public RPC if available
        try:
            return get_random_rpc(ecosystem, network)
        except KeyError:
            return None

    @property
    def connection_str(self) -> str:
        return self.uri or f"{self.ipc_path}"

    @property
    def connection_id(self) -> Optional[str]:
        return f"{self.network_choice}:{self.uri}"

    @property
    def _clean_uri(self) -> str:
        uri = self.uri
        return sanitize_url(uri) if _is_http_url(uri) or _is_ws_url(uri) else uri

    @property
    def ipc_path(self) -> Path:
        if ipc := self.settings.ipc_path:
            return ipc

        config: dict = self.config.get(self.network.ecosystem.name, {})
        network_config = config.get(self.network.name, {})
        if ipc := network_config.get("ipc_path"):
            return Path(ipc)

        # Check `uri:` config.
        uri = self.uri
        if _is_ipc_path(uri):
            return Path(uri)

        # Default (used by geth-process).
        return self.data_dir / "geth.ipc"

    @property
    def data_dir(self) -> Path:
        if self.settings.data_dir:
            return self.settings.data_dir.expanduser()

        return _get_default_data_dir()

    @cached_property
    def _ots_api_level(self) -> Optional[int]:
        # NOTE: Returns None when OTS namespace is not enabled.
        try:
            result = self.make_request("ots_getApiLevel")
        except (NotImplementedError, ApeException, ValueError):
            return None

        if isinstance(result, int):
            return result

        elif isinstance(result, str) and result.isnumeric():
            return int(result)

        return None

    def _set_web3(self):
        # Clear cached version when connecting to another URI.
        self._client_version = None
        headers = self.network_manager.get_request_headers(
            self.network.ecosystem.name, self.network.name, self.name
        )
        self._web3 = _create_web3(
            http_uri=self.http_uri,
            ipc_path=self.ipc_path,
            ws_uri=self.ws_uri,
            request_kwargs={"headers": headers},
        )

    def _complete_connect(self):
        client_version = self.client_version.lower()
        if "geth" in client_version:
            self._log_connection("Geth")
        elif "reth" in client_version:
            self._log_connection("Reth")
        elif "erigon" in client_version:
            self._log_connection("Erigon")
            self.concurrency = 8
            self.block_page_size = 40_000
        elif "nethermind" in client_version:
            self._log_connection("Nethermind")
            self.concurrency = 32
            self.block_page_size = 50_000
        else:
            client_name = client_version.partition("/")[0]
            logger.info(f"Connecting to a '{client_name}' node.")

        if not self.network.is_dev:
            self.web3.eth.set_gas_price_strategy(rpc_gas_price_strategy)

        # Check for chain errors, including syncing
        try:
            chain_id = self.web3.eth.chain_id
        except ValueError as err:
            raise ProviderError(
                err.args[0].get("message")
                if all((hasattr(err, "args"), err.args, isinstance(err.args[0], dict)))
                else "Error getting chain id."
            )

        # NOTE: We have to check both earliest and latest
        #   because if the chain was _ever_ PoA, we need
        #   this middleware.
        for option in ("earliest", "latest"):
            try:
                block = self.web3.eth.get_block(option)  # type: ignore[arg-type]
            except ExtraDataLengthError:
                is_likely_poa = True
                break
            else:
                is_likely_poa = (
                    "proofOfAuthorityData" in block
                    or len(block.get("extraData", "")) > MAX_EXTRADATA_LENGTH
                )
                if is_likely_poa:
                    break

        if is_likely_poa and ExtraDataToPOAMiddleware not in self.web3.middleware_onion:
            self.web3.middleware_onion.inject(ExtraDataToPOAMiddleware, layer=0)

        self.network.verify_chain_id(chain_id)

    def disconnect(self):
        self._call_trace_approach = None
        self._web3 = None
        self._client_version = None

    def _log_connection(self, client_name: str):
        msg = f"Connecting to existing {client_name.strip()} node at"
        suffix = (
            self.ipc_path.as_posix().replace(Path.home().as_posix(), "$HOME")
            if self.ipc_path.exists()
            else self._clean_uri
        )
        logger.info(f"{msg} {suffix}.")

    def ots_get_contract_creator(self, address: AddressType) -> Optional[dict]:
        if self._ots_api_level is None:
            return None

        result = self.make_request("ots_getContractCreator", [address])
        if result is None:
            # NOTE: Skip the explorer part of the error message via `has_explorer=True`.
            raise ContractNotFoundError(address, True, self.network_choice)

        return result

    def _get_contract_creation_receipt(self, address: AddressType) -> Optional[ReceiptAPI]:
        if result := self.ots_get_contract_creator(address):
            tx_hash = result["hash"]
            return self.get_receipt(tx_hash)

        return None

    def connect(self):
        self._set_web3()
        if not self.is_connected:
            uri = self._clean_uri
            message = f"No (supported) node found on '{uri}'."
            raise ProviderError(message)

        self._complete_connect()


def _create_web3(
    http_uri: Optional[str] = None,
    ipc_path: Optional[Path] = None,
    ws_uri: Optional[str] = None,
    request_kwargs: Optional[dict] = None,
):
    # NOTE: This list is ordered by try-attempt.
    # Try ENV, then IPC, and then HTTP last.
    providers: list = [load_provider_from_environment]
    if ipc := ipc_path:
        providers.append(lambda: IPCProvider(ipc_path=ipc))
    if http := http_uri:
        request_kwargs = request_kwargs or {}
        if "timeout" not in request_kwargs:
            request_kwargs["timeout"] = 30 * 60

        providers.append(lambda: HTTPProvider(endpoint_uri=http, request_kwargs=request_kwargs))
    if ws := ws_uri:
        providers.append(lambda: WebSocketProvider(endpoint_uri=ws))

    provider = AutoProvider(potential_providers=providers)
    return Web3(provider)


def _get_default_data_dir() -> Path:
    # Modified from web3.py package to always return IPC even when none exist.
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Ethereum"

    elif sys.platform.startswith("linux") or sys.platform.startswith("freebsd"):
        return Path.home() / "ethereum"

    elif sys.platform == "win32":
        return Path(os.path.join("\\\\", ".", "pipe"))

    else:
        raise ValueError(
            f"Unsupported platform '{sys.platform}'.  Only darwin/linux/win32/"
            "freebsd are supported.  You must specify the data_dir."
        )


def _is_uri(val: str) -> bool:
    return _is_http_url(val) or _is_ws_url(val) or _is_ipc_path(val)


def _is_http_url(val: str) -> bool:
    return val.startswith("https://") or val.startswith("http://")


def _is_ws_url(val: str) -> bool:
    return val.startswith("wss://") or val.startswith("ws://")


def _is_ipc_path(val: str) -> bool:
    return val.endswith(".ipc")


class _LazyCallTrace(ManagerAccessMixin):
    def __init__(self, eth_call_args: list):
        self._arguments = eth_call_args

        self.contract_type = None

    @cached_property
    def trace(self) -> CallTrace:
        return CallTrace(
            tx=self._arguments[0], arguments=self._arguments[1:], use_tokens_for_symbols=True
        )

    @cached_property
    def source_traceback(self) -> Optional[SourceTraceback]:
        ct = self.contract_type
        if ct is None:
            return None

        method_id = self._arguments[0].get("data", "")[:10] or None
        if ct and method_id:
            if contract_src := self.local_project._create_contract_source(ct):
                return SourceTraceback.create(contract_src, self.trace, method_id)

        return None
