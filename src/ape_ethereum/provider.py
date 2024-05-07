import os
import re
import sys
import time
from abc import ABC
from concurrent.futures import ThreadPoolExecutor
from copy import copy
from functools import cached_property, wraps
from itertools import tee
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional, Tuple, Union, cast

import ijson  # type: ignore
import requests
from eth_pydantic_types import HexBytes
from eth_typing import BlockNumber, HexStr
from eth_utils import add_0x_prefix, is_hex, to_hex
from ethpm_types import EventABI
from evm_trace import CallTreeNode as EvmCallTreeNode
from evm_trace import ParityTraceList
from evm_trace import TraceFrame as EvmTraceFrame
from evm_trace import (
    create_trace_frames,
    get_calltree_from_geth_call_trace,
    get_calltree_from_parity_trace,
)
from pydantic.dataclasses import dataclass
from web3 import HTTPProvider, IPCProvider, Web3
from web3.exceptions import ContractLogicError as Web3ContractLogicError
from web3.exceptions import (
    ExtraDataLengthError,
    MethodUnavailable,
    TimeExhausted,
    TransactionNotFound,
)
from web3.gas_strategies.rpc import rpc_gas_price_strategy
from web3.middleware import geth_poa_middleware
from web3.middleware.validation import MAX_EXTRADATA_LENGTH
from web3.providers import AutoProvider
from web3.providers.auto import load_provider_from_environment
from web3.types import FeeHistory, RPCEndpoint, TxParams

from ape.api import Address, BlockAPI, ProviderAPI, ReceiptAPI, TransactionAPI
from ape.api.networks import LOCAL_NETWORK_NAME
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
from ape.types import (
    AddressType,
    AutoGasLimit,
    BlockID,
    CallTreeNode,
    ContractCode,
    ContractLog,
    LogFilter,
    SourceTraceback,
    TraceFrame,
)
from ape.utils import gas_estimation_error_message, to_int
from ape.utils.misc import DEFAULT_MAX_RETRIES_TX
from ape_ethereum._print import CONSOLE_CONTRACT_ID, console_contract
from ape_ethereum.transactions import AccessList, AccessListTransaction

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
        if (
            hasattr(self.web3.provider, "endpoint_uri")
            and isinstance(self.web3.provider.endpoint_uri, str)
            and self.web3.provider.endpoint_uri.startswith("http")
        ):
            return self.web3.provider.endpoint_uri

        elif uri := getattr(self, "uri", None):
            # NOTE: Some providers define this
            return uri

        return None

    @property
    def ws_uri(self) -> Optional[str]:
        if (
            hasattr(self.web3.provider, "endpoint_uri")
            and isinstance(self.web3.provider.endpoint_uri, str)
            and self.web3.provider.endpoint_uri.startswith("ws")
        ):
            return self.web3.provider.endpoint_uri

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
        latest_block_number = self.get_block("latest").number
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

        return pending_base_fee

    def _get_fee_history(self, block_number: int) -> FeeHistory:
        try:
            return self.web3.eth.fee_history(1, BlockNumber(block_number), reward_percentiles=[])
        except (MethodUnavailable, AttributeError) as err:
            raise APINotImplementedError(str(err)) from err

    def _get_last_base_fee(self) -> int:
        block = self.get_block("latest")
        base_fee = getattr(block, "base_fee", None)
        if base_fee is not None:
            return base_fee

        raise APINotImplementedError("No base fee found in block.")

    @property
    def is_connected(self) -> bool:
        if self._web3 is None:
            return False

        return self._web3.is_connected()

    @property
    def max_gas(self) -> int:
        block = self.web3.eth.get_block("latest")
        return block["gasLimit"]

    @cached_property
    def supports_tracing(self) -> bool:
        try:
            # NOTE: Txn hash is purposely not a real hash.
            # If we get any exception besides not implemented error,
            # then we support tracing on this provider.
            self.get_call_tree("__CHECK_IF_SUPPORTS_TRACING__")
        except APINotImplementedError:
            return False
        except Exception:
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
            txn_dict["type"] = HexBytes(txn_dict["type"]).hex()

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
            tx_to_trace: Dict = {}
            for key, val in txn_params.items():
                if isinstance(val, int):
                    tx_to_trace[key] = hex(val)
                else:
                    tx_to_trace[key] = val

            try:
                call_trace = self._trace_call([tx_to_trace, "latest"])
            except Exception:
                call_trace = None

            traces = None
            tb = None
            if call_trace and txn_params.get("to"):
                traces = (self._create_trace_frame(t) for t in call_trace[1])
                try:
                    if contract_type := self.chain_manager.contracts.get(txn_params["to"]):
                        tb = SourceTraceback.create(
                            contract_type, traces, HexBytes(txn_params["data"])
                        )
                except ProviderNotConnectedError:
                    pass

            tx_error = self.get_virtual_machine_error(
                err,
                txn=txn,
                trace=traces,
                source_traceback=tb,
            )

            # If this is the cause of a would-be revert,
            # raise ContractLogicError so that we can confirm tx-reverts.
            if isinstance(tx_error, ContractLogicError):
                raise tx_error from err

            message = gas_estimation_error_message(tx_error)
            raise TransactionError(
                message, base_err=tx_error, txn=txn, source_traceback=tx_error.source_traceback
            ) from err

    def _trace_call(self, arguments: List[Any]) -> Tuple[Dict, Iterator[EvmTraceFrame]]:
        result = self._make_request("debug_traceCall", arguments)
        trace_data = result.get("structLogs", [])
        return result, create_trace_frames(trace_data)

    @cached_property
    def chain_id(self) -> int:
        default_chain_id = None
        if (
            self.network.name
            not in (
                "custom",
                LOCAL_NETWORK_NAME,
            )
            and not self.network.is_fork
        ):
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

        # Some nodes (like anvil) will not have a base fee if set to 0.
        if "baseFeePerGas" in block_data and block_data.get("baseFeePerGas") is None:
            block_data["baseFeePerGas"] = 0

        return self.network.ecosystem.decode_block(block_data)

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

    def send_call(
        self,
        txn: TransactionAPI,
        block_id: Optional[BlockID] = None,
        state: Optional[Dict] = None,
        **kwargs,
    ) -> HexBytes:
        if block_id is not None:
            kwargs["block_identifier"] = block_id
        if kwargs.pop("skip_trace", False):
            return self._send_call(txn, **kwargs)
        elif self._test_runner is not None:
            track_gas = self._test_runner.gas_tracker.enabled
            track_coverage = self._test_runner.coverage_tracker.enabled
        else:
            track_gas = False
            track_coverage = False

        show_trace = kwargs.pop("show_trace", False)
        show_gas = kwargs.pop("show_gas_report", False)
        needs_trace = track_gas or track_coverage or show_trace or show_gas
        if not needs_trace or not self.provider.supports_tracing or not txn.receiver:
            return self._send_call(txn, **kwargs)

        # The user is requesting information related to a call's trace,
        # such as gas usage data.
        try:
            with self.chain_manager.isolate():
                return self._send_call_as_txn(
                    txn,
                    track_gas=track_gas,
                    track_coverage=track_coverage,
                    show_trace=show_trace,
                    show_gas=show_gas,
                    **kwargs,
                )

        except APINotImplementedError:
            return self._send_call(txn, **kwargs)

    def _send_call_as_txn(
        self,
        txn: TransactionAPI,
        track_gas: bool = False,
        track_coverage: bool = False,
        show_trace: bool = False,
        show_gas: bool = False,
        **kwargs,
    ) -> HexBytes:
        account = self.account_manager.test_accounts[0]
        receipt = account.call(txn, **kwargs)
        if not (call_tree := receipt.call_tree):
            return self._send_call(txn, **kwargs)

        # Grab raw returndata before enrichment
        returndata = call_tree.outputs

        if (track_gas or track_coverage) and show_gas and not show_trace:
            # Optimization to enrich early and in_place=True.
            call_tree.enrich()

        if track_gas:
            # in_place=False in case show_trace is True
            receipt.track_gas()

        if track_coverage:
            receipt.track_coverage()

        if show_gas:
            # in_place=False in case show_trace is True
            self.chain_manager._reports.show_gas(call_tree.enrich(in_place=False))

        if show_trace:
            call_tree = call_tree.enrich(use_symbol_for_tokens=True)
            self.chain_manager._reports.show_trace(call_tree)

        return HexBytes(returndata)

    def _send_call(self, txn: TransactionAPI, **kwargs) -> HexBytes:
        arguments = self._prepare_call(txn, **kwargs)
        try:
            return self._eth_call(arguments)
        except TransactionError as err:
            if not err.txn:
                err.txn = txn

            raise  # The tx error

    def _eth_call(self, arguments: List) -> HexBytes:
        # Force the usage of hex-type to support a wider-range of nodes.
        txn_dict = copy(arguments[0])
        if isinstance(txn_dict.get("type"), int):
            txn_dict["type"] = HexBytes(txn_dict["type"]).hex()

        # Remove unnecessary values to support a wider-range of nodes.
        txn_dict.pop("chainId", None)

        arguments[0] = txn_dict
        try:
            result = self._make_request("eth_call", arguments)
        except Exception as err:
            receiver = txn_dict.get("to")
            raise self.get_virtual_machine_error(err, contract_address=receiver) from err

        if "error" in result:
            raise ProviderError(result["error"]["message"])

        return HexBytes(result)

    def _prepare_call(self, txn: TransactionAPI, **kwargs) -> List:
        # NOTE: Using JSON mode since used as request data.
        txn_dict = txn.model_dump(by_alias=True, mode="json")
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
        try:
            receipt_data = self.web3.eth.wait_for_transaction_receipt(hex_hash, timeout=timeout)
        except TimeExhausted as err:
            raise TransactionNotFoundError(txn_hash, error_messsage=str(err)) from err

        ecosystem_config = self.network.config.model_dump(by_alias=True)
        network_config: Dict = ecosystem_config.get(self.network.name, {})
        max_retries = network_config.get("max_get_transaction_retries", DEFAULT_MAX_RETRIES_TX)
        txn = {}
        for attempt in range(max_retries):
            try:
                txn = dict(self.web3.eth.get_transaction(HexStr(txn_hash)))
                break
            except TransactionNotFound:
                if attempt < max_retries - 1:  # if this wasn't the last attempt
                    time.sleep(1)  # Wait for 1 second before retrying.
                    continue  # Continue to the next iteration, effectively retrying the operation.
                else:  # if it was the last attempt
                    raise  # Re-raise the last exception.

        data = {
            "provider": self,
            "required_confirmations": required_confirmations,
            **txn,
            **receipt_data,
        }
        receipt = self.network.ecosystem.decode_receipt(data)
        return receipt.await_confirmations()

    def get_transactions_by_block(self, block_id: BlockID) -> Iterator[TransactionAPI]:
        if isinstance(block_id, str):
            block_id = HexStr(block_id)

            if block_id.isnumeric():
                block_id = add_0x_prefix(block_id)

        block = cast(Dict, self.web3.eth.get_block(block_id, full_transactions=True))
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
                    yield self.get_receipt(txn.txn_hash.hex())

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
        last = YieldAction(number=last_num, hash=last_hash, time=time.time())

        # A helper method for various points of ensuring we didn't timeout.
        def assert_chain_activity():
            time_waiting = time.time() - last.time
            if time_waiting > timeout:
                raise ProviderError("Timed out waiting for next block.")

        # Begin the daemon.
        while True:
            # The next block we want is simply 1 after the last.
            next_block = last.number + 1

            head = self.get_block("latest")

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
        topics: Optional[List[Union[str, List[str]]]] = None,
        required_confirmations: Optional[int] = None,
        new_block_timeout: Optional[int] = None,
        events: Optional[List[EventABI]] = None,
    ) -> Iterator[ContractLog]:
        events = events or []
        if required_confirmations is None:
            required_confirmations = self.network.required_confirmations

        if stop_block is not None:
            if stop_block <= (self.provider.get_block("latest").number or 0):
                raise ValueError("'stop' argument must be in the future.")

        for block in self.poll_blocks(stop_block, required_confirmations, new_block_timeout):
            if block.number is None:
                raise ValueError("Block number cannot be None")

            log_params: Dict[str, Any] = {
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

    def get_contract_creation_receipts(
        self,
        address: AddressType,
        start_block: int = 0,
        stop_block: Optional[int] = None,
        contract_code: Optional[HexBytes] = None,
    ) -> Iterator[ReceiptAPI]:
        if stop_block is None:
            stop_block = self.chain_manager.blocks.height

        if contract_code is None:
            contract_code = HexBytes(self.get_code(address))

        mid_block = (stop_block - start_block) // 2 + start_block
        # NOTE: biased towards mid_block == start_block

        if start_block == mid_block:
            for tx in self.chain_manager.blocks[mid_block].transactions:
                if (receipt := tx.receipt) and receipt.contract_address == address:
                    yield receipt

            if mid_block + 1 <= stop_block:
                yield from self.get_contract_creation_receipts(
                    address,
                    start_block=mid_block + 1,
                    stop_block=stop_block,
                    contract_code=contract_code,
                )

        # TODO: Handle when code is nonzero but doesn't match
        # TODO: Handle when code is empty after it's not (re-init)
        elif HexBytes(self.get_code(address, block_id=mid_block)) == contract_code:
            # If the code exists, we need to look backwards.
            yield from self.get_contract_creation_receipts(
                address,
                start_block=start_block,
                stop_block=mid_block,
                contract_code=contract_code,
            )

        elif mid_block + 1 <= stop_block:
            # The code does not exist yet, we need to look ahead.
            yield from self.get_contract_creation_receipts(
                address,
                start_block=mid_block + 1,
                stop_block=stop_block,
                contract_code=contract_code,
            )

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

            logs = self._make_request("eth_getLogs", [filter_params])
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
        try:
            if txn.signature or not txn.sender:
                txn_hash = self.web3.eth.send_raw_transaction(txn.serialize_transaction())
            else:
                if txn.sender not in self.web3.eth.accounts:
                    self.chain_manager.provider.unlock_account(txn.sender)

                # NOTE: Using JSON mode since used as request data.
                txn_data = cast(TxParams, txn.model_dump(by_alias=True, mode="json"))
                txn_hash = self.web3.eth.send_transaction(txn_data)

        except (ValueError, Web3ContractLogicError) as err:
            vm_err = self.get_virtual_machine_error(err, txn=txn)
            raise vm_err from err

        receipt = self.get_receipt(
            txn_hash.hex(),
            required_confirmations=(
                txn.required_confirmations
                if txn.required_confirmations is not None
                else self.network.required_confirmations
            ),
        )

        # NOTE: Ensure to cache even the failed receipts.
        # NOTE: Caching must happen before error enrichment.
        self.chain_manager.history.append(receipt)

        if receipt.failed:
            # NOTE: Using JSON mode since used as request data.
            txn_dict = receipt.transaction.model_dump(by_alias=True, mode="json")

            txn_params = cast(TxParams, txn_dict)

            # Replay txn to get revert reason
            try:
                self.web3.eth.call(txn_params)
            except Exception as err:
                vm_err = self.get_virtual_machine_error(err, txn=txn)
                raise vm_err from err

            # If we get here, for some reason the tx-replay did not produce
            # a VM error.
            receipt.raise_for_status()

        return receipt

    def _post_send_transaction(self, tx: TransactionAPI, receipt: ReceiptAPI):
        """Execute post-transaction ops"""

        # TODO: Optional configuration?
        if tx.receiver and Address(tx.receiver).is_contract:
            # Look for and print any contract logging
            receipt.show_debug_logs()

        logger.info(f"Confirmed {receipt.txn_hash} (total fees paid = {receipt.total_fees_paid})")

    def _post_connect(self):
        # Register the console contract for trace enrichment
        self.chain_manager.contracts._cache_contract_type(CONSOLE_CONTRACT_ID, console_contract)

    def _create_call_tree_node(
        self, evm_call: EvmCallTreeNode, txn_hash: Optional[str] = None
    ) -> CallTreeNode:
        address = evm_call.address
        try:
            contract_id = str(self.provider.network.ecosystem.decode_address(address))
        except ValueError:
            # Use raw value since it is not a real address.
            contract_id = address.hex()

        call_type = evm_call.call_type.value
        return CallTreeNode(
            calls=[self._create_call_tree_node(x, txn_hash=txn_hash) for x in evm_call.calls],
            call_type=call_type,
            contract_id=contract_id,
            failed=evm_call.failed,
            gas_cost=evm_call.gas_cost,
            inputs=evm_call.calldata if "CREATE" in call_type else evm_call.calldata[4:].hex(),
            method_id=evm_call.calldata[:4].hex(),
            outputs=evm_call.returndata.hex(),
            raw=evm_call.model_dump(by_alias=True),
            txn_hash=txn_hash,
        )

    def _create_trace_frame(self, evm_frame: EvmTraceFrame) -> TraceFrame:
        address_bytes = evm_frame.address
        try:
            address = (
                self.network.ecosystem.decode_address(address_bytes.hex())
                if address_bytes
                else None
            )
        except ValueError:
            # Might not be a real address.
            address = cast(AddressType, address_bytes.hex()) if address_bytes else None

        return TraceFrame(
            pc=evm_frame.pc,
            op=evm_frame.op,
            gas=evm_frame.gas,
            gas_cost=evm_frame.gas_cost,
            depth=evm_frame.depth,
            contract_address=address,
            raw=evm_frame.model_dump(by_alias=True),
        )

    def _make_request(self, endpoint: str, parameters: Optional[List] = None) -> Any:
        parameters = parameters or []
        result = self.web3.provider.make_request(RPCEndpoint(endpoint), parameters)

        if "error" in result:
            error = result["error"]
            message = (
                error["message"] if isinstance(error, dict) and "message" in error else str(error)
            )

            if (
                "does not exist/is not available" in str(message)
                or re.match(r"Method .*?not found", message)
                or message.startswith("Unknown RPC Endpoint")
                or "RPC Endpoint has not been implemented" in message
            ):
                raise APINotImplementedError(
                    f"RPC method '{endpoint}' is not implemented by this node instance."
                )

            raise ProviderError(message)

        elif "result" in result:
            return result.get("result", {})

        return result

    def create_access_list(
        self, transaction: TransactionAPI, block_id: Optional[BlockID] = None
    ) -> List[AccessList]:
        """
        Get the access list for a transaction use ``eth_createAccessList``.

        Args:
            transaction (:class:`~ape.api.transactions.TransactionAPI`): The
              transaction to check.
            block_id (:class:`~ape.types.BlockID`): Optionally specify a block
              ID. Defaults to using the latest block.

        Returns:
            List[:class:`~ape_ethereum.transactions.AccessList`]
        """
        # NOTE: Using JSON mode since used in request data.
        tx_dict = transaction.model_dump(by_alias=True, mode="json", exclude=("chain_id",))
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

        result = self._make_request("eth_createAccessList", arguments)
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
            return VirtualMachineError(base_err=exception, **kwargs)

        elif not (err_msg := err_data.get("message")):
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
        trace: Optional[Iterator[TraceFrame]] = None,
        contract_address: Optional[AddressType] = None,
        source_traceback: Optional[SourceTraceback] = None,
    ) -> ContractLogicError:
        if hasattr(exception, "args") and len(exception.args) == 2:
            message = exception.args[0].replace("execution reverted: ", "")
            data = exception.args[1]
        else:
            message = str(exception).split(":")[-1].strip()
            data = None

        params: Dict = {
            "trace": trace,
            "contract_address": contract_address,
            "source_traceback": source_traceback,
        }
        no_reason = message == "execution reverted"

        if isinstance(exception, Web3ContractLogicError) and no_reason:
            if data is None:
                # Check for custom exception data and use that as the message instead.
                # This allows compiler exception enrichment to function.
                err_trace = None
                try:
                    if trace:
                        trace, err_trace = tee(trace)
                    elif txn:
                        err_trace = self.provider.get_transaction_trace(txn.txn_hash.hex())

                    try:
                        trace_ls: List[TraceFrame] = list(err_trace) if err_trace else []
                    except Exception as err:
                        logger.error(f"Failed getting traceback: {err}")
                        trace_ls = []

                    data = trace_ls[-1].raw if len(trace_ls) > 0 else {}
                    memory = data.get("memory", [])
                    return_value = "".join([x[2:] for x in memory[4:]])
                    if return_value:
                        message = f"0x{return_value}"
                        no_reason = False

                except (ApeException, NotImplementedError):
                    # Either provider does not support or isn't a custom exception.
                    pass

            elif data != "no data" and is_hex(data):
                message = add_0x_prefix(data)

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

    name: str = "geth"

    can_use_parity_traces: Optional[bool] = None
    """Is ``None`` until known."""

    @property
    def uri(self) -> str:
        if "url" in self.provider_settings:
            raise ConfigError("Unknown provider setting 'url'. Did you mean 'uri'?")

        elif "uri" in self.provider_settings:
            # Use adhoc, scripted value
            return self.provider_settings["uri"]

        config = self.config.model_dump().get(self.network.ecosystem.name, None)
        if config is None:
            return DEFAULT_SETTINGS["uri"]

        # Use value from config file
        network_config = config.get(self.network.name) or DEFAULT_SETTINGS

        if "url" in network_config:
            raise ConfigError("Unknown provider setting 'url'. Did you mean 'uri'?")

        settings_uri = network_config.get("uri", DEFAULT_SETTINGS["uri"])
        if _is_url(settings_uri):
            return settings_uri

        # Likely was an IPC Path and will connect that way.
        return ""

    @property
    def connection_str(self) -> str:
        return self.uri or f"{self.ipc_path}"

    @property
    def connection_id(self) -> Optional[str]:
        return f"{self.network_choice}:{self.uri}"

    @property
    def _clean_uri(self) -> str:
        return sanitize_url(self.uri) if _is_url(self.uri) else self.uri

    @property
    def ipc_path(self) -> Path:
        return self.settings.ipc_path or self.data_dir / "geth.ipc"

    @property
    def data_dir(self) -> Path:
        if self.settings.data_dir:
            return self.settings.data_dir.expanduser()

        return _get_default_data_dir()

    @cached_property
    def _ots_api_level(self) -> Optional[int]:
        # NOTE: Returns None when OTS namespace is not enabled.
        try:
            result = self._make_request("ots_getApiLevel")
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
        self._web3 = _create_web3(self.uri, ipc_path=self.ipc_path)

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
            client_name = client_version.split("/")[0]
            logger.info(f"Connecting to a '{client_name}' node.")

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

        if is_likely_poa and geth_poa_middleware not in self.web3.middleware_onion:
            self.web3.middleware_onion.inject(geth_poa_middleware, layer=0)

        self.network.verify_chain_id(chain_id)

    def disconnect(self):
        self.can_use_parity_traces = None
        self._web3 = None
        self._client_version = None

    def get_transaction_trace(self, txn_hash: Union[HexBytes, str]) -> Iterator[TraceFrame]:
        if isinstance(txn_hash, HexBytes):
            txn_hash_str = str(to_hex(txn_hash))
        else:
            txn_hash_str = txn_hash

        frames = self._stream_request(
            "debug_traceTransaction",
            [txn_hash_str, {"enableMemory": True}],
            "result.structLogs.item",
        )
        for frame in create_trace_frames(frames):
            yield self._create_trace_frame(frame)

    def _get_transaction_trace_using_call_tracer(self, txn_hash: str) -> Dict:
        return self._make_request(
            "debug_traceTransaction", [txn_hash, {"enableMemory": True, "tracer": "callTracer"}]
        )

    def get_call_tree(self, txn_hash: str) -> CallTreeNode:
        if self.can_use_parity_traces is True:
            return self._get_parity_call_tree(txn_hash)

        elif self.can_use_parity_traces is False:
            return self._get_geth_call_tree(txn_hash)

        elif "erigon" in self.client_version.lower():
            tree = self._get_parity_call_tree(txn_hash)
            self.can_use_parity_traces = True
            return tree

        try:
            # Try the Parity traces first, in case node client supports it.
            tree = self._get_parity_call_tree(txn_hash)
        except (ValueError, APINotImplementedError, ProviderError):
            self.can_use_parity_traces = False
            return self._get_geth_call_tree(txn_hash)

        # Parity style works.
        self.can_use_parity_traces = True
        return tree

    def _get_parity_call_tree(self, txn_hash: str) -> CallTreeNode:
        result = self._make_request("trace_transaction", [txn_hash])
        if not result:
            raise ProviderError(f"Failed to get trace for '{txn_hash}'.")

        traces = ParityTraceList.model_validate(result)
        evm_call = get_calltree_from_parity_trace(traces)
        return self._create_call_tree_node(evm_call, txn_hash=txn_hash)

    def _get_geth_call_tree(self, txn_hash: str) -> CallTreeNode:
        calls = self._get_transaction_trace_using_call_tracer(txn_hash)
        evm_call = get_calltree_from_geth_call_trace(calls)
        return self._create_call_tree_node(evm_call, txn_hash=txn_hash)

    def _log_connection(self, client_name: str):
        msg = f"Connecting to existing {client_name.strip()} node at"
        suffix = (
            self.ipc_path.as_posix().replace(Path.home().as_posix(), "$HOME")
            if self.ipc_path.exists()
            else self._clean_uri
        )
        logger.info(f"{msg} {suffix}.")

    def ots_get_contract_creator(self, address: AddressType) -> Optional[Dict]:
        if self._ots_api_level is None:
            return None

        result = self._make_request("ots_getContractCreator", [address])
        if result is None:
            # NOTE: Skip the explorer part of the error message via `has_explorer=True`.
            raise ContractNotFoundError(address, has_explorer=True, provider_name=self.name)

        return result

    def _get_contract_creation_receipt(self, address: AddressType) -> Optional[ReceiptAPI]:
        if result := self.ots_get_contract_creator(address):
            tx_hash = result["hash"]
            return self.get_receipt(tx_hash)

        return None

    def _stream_request(self, method: str, params: List, iter_path="result.item"):
        payload = {"jsonrpc": "2.0", "id": 1, "method": method, "params": params}
        results = ijson.sendable_list()
        coroutine = ijson.items_coro(results, iter_path)
        resp = requests.post(self.uri, json=payload, stream=True)
        resp.raise_for_status()

        for chunk in resp.iter_content(chunk_size=2**17):
            coroutine.send(chunk)
            yield from results
            del results[:]

    def connect(self):
        self._set_web3()
        if not self.is_connected:
            uri = self._clean_uri
            message = f"No (supported) node found on '{uri}'."
            raise ProviderError(message)

        self._complete_connect()


def _create_web3(uri: str, ipc_path: Optional[Path] = None):
    # Separated into helper method for testing purposes.
    def http_provider():
        return HTTPProvider(uri, request_kwargs={"timeout": 30 * 60})

    def ipc_provider():
        # NOTE: This mypy complaint seems incorrect.
        if not (path := ipc_path):
            raise ValueError("IPC Path required.")

        return IPCProvider(ipc_path=path)

    # NOTE: This list is ordered by try-attempt.
    # Try ENV, then IPC, and then HTTP last.
    providers = [load_provider_from_environment]
    if ipc_path:
        providers.append(ipc_provider)
    if uri:
        providers.append(http_provider)

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


def _is_url(val: str) -> bool:
    return (
        val.startswith("https://")
        or val.startswith("http://")
        or val.startswith("wss://")
        or val.startswith("ws://")
    )
