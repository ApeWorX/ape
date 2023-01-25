import shutil
from abc import ABC
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional, Union

import ijson  # type: ignore
import requests
from eth_typing import HexStr
from eth_utils import add_0x_prefix, to_hex, to_wei
from evm_trace import CallType, ParityTraceList
from evm_trace import TraceFrame as EvmTraceFrame
from evm_trace import (
    get_calltree_from_geth_call_trace,
    get_calltree_from_geth_trace,
    get_calltree_from_parity_trace,
)
from geth import LoggingMixin  # type: ignore
from geth.accounts import ensure_account_exists  # type: ignore
from geth.chain import initialize_chain  # type: ignore
from geth.process import BaseGethProcess  # type: ignore
from geth.wrapper import construct_test_chain_kwargs  # type: ignore
from hexbytes import HexBytes
from pydantic import Extra
from requests.exceptions import ConnectionError
from web3 import HTTPProvider, Web3
from web3.exceptions import ExtraDataLengthError
from web3.gas_strategies.rpc import rpc_gas_price_strategy
from web3.middleware import geth_poa_middleware
from web3.middleware.validation import MAX_EXTRADATA_LENGTH
from yarl import URL

from ape.api import PluginConfig, TestProviderAPI, TransactionAPI, UpstreamProvider, Web3Provider
from ape.exceptions import APINotImplementedError, ProviderError
from ape.logging import logger
from ape.types import CallTreeNode, SnapshotID, TraceFrame
from ape.utils import (
    DEFAULT_NUMBER_OF_TEST_ACCOUNTS,
    DEFAULT_TEST_MNEMONIC,
    generate_dev_accounts,
    raises_not_implemented,
)

DEFAULT_PORT = 8545
DEFAULT_HOSTNAME = "localhost"
DEFAULT_SETTINGS = {"uri": f"http://{DEFAULT_HOSTNAME}:{DEFAULT_PORT}"}
GETH_DEV_CHAIN_ID = 1337


class GethDevProcess(LoggingMixin, BaseGethProcess):
    """
    A developer-configured geth that only exists until disconnected.
    """

    def __init__(
        self,
        base_directory: Path,
        hostname: str = DEFAULT_HOSTNAME,
        port: int = DEFAULT_PORT,
        mnemonic: str = DEFAULT_TEST_MNEMONIC,
        number_of_accounts: int = DEFAULT_NUMBER_OF_TEST_ACCOUNTS,
        chain_id: int = GETH_DEV_CHAIN_ID,
        initial_balance: Union[str, int] = to_wei(10000, "ether"),
    ):
        if not shutil.which("geth"):
            raise GethNotInstalledError()

        self.data_dir = base_directory / "dev"
        self._hostname = hostname
        self._port = port
        geth_kwargs = construct_test_chain_kwargs(
            data_dir=self.data_dir,
            rpc_addr=hostname,
            rpc_port=port,
            network_id=chain_id,
            ws_enabled=False,
            ws_addr=None,
            ws_origins=None,
            ws_port=None,
            ws_api=None,
        )

        # Ensure a clean data-dir.
        self._clean()

        sealer = ensure_account_exists(**geth_kwargs).decode().replace("0x", "")
        accounts = generate_dev_accounts(mnemonic, number_of_accounts=number_of_accounts)
        genesis_data: Dict = {
            "overwrite": True,
            "coinbase": "0x0000000000000000000000000000000000000000",
            "difficulty": "0x0",
            "extraData": f"0x{'0' * 64}{sealer}{'0' * 130}",
            "config": {
                "chainId": chain_id,
                "gasLimit": 0,
                "homesteadBlock": 0,
                "difficulty": "0x0",
                "eip150Block": 0,
                "eip155Block": 0,
                "eip158Block": 0,
                "byzantiumBlock": 0,
                "constantinopleBlock": 0,
                "petersburgBlock": 0,
                "istanbulBlock": 0,
                "berlinBlock": 0,
                "londonBlock": 0,
                "parisBlock": 0,
                "clique": {"period": 0, "epoch": 30000},
            },
            "alloc": {a.address: {"balance": str(initial_balance)} for a in accounts},
        }

        def make_logs_paths(stream_name: str):
            path = base_directory / "geth-logs" / f"{stream_name}_{self._port}"
            path.parent.mkdir(exist_ok=True, parents=True)
            return path

        initialize_chain(genesis_data, **geth_kwargs)

        super().__init__(
            geth_kwargs,
            stdout_logfile_path=make_logs_paths("stdout"),
            stderr_logfile_path=make_logs_paths("stderr"),
        )

    @classmethod
    def from_uri(cls, uri: str, data_folder: Path, **kwargs):
        parsed_uri = URL(uri)

        if parsed_uri.host not in ("localhost", "127.0.0.1"):
            raise ConnectionError(f"Unable to start Geth on non-local host {parsed_uri.host}.")

        port = parsed_uri.port if parsed_uri.port is not None else DEFAULT_PORT
        mnemonic = kwargs.get("mnemonic", DEFAULT_TEST_MNEMONIC)
        number_of_accounts = kwargs.get("number_of_accounts", DEFAULT_NUMBER_OF_TEST_ACCOUNTS)
        return cls(
            data_folder,
            hostname=parsed_uri.host,
            port=port,
            mnemonic=mnemonic,
            number_of_accounts=number_of_accounts,
        )

    def connect(self):
        logger.info(f"Starting geth with RPC address '{self._hostname}:{self._port}'.")
        self.start()
        self.wait_for_rpc(timeout=60)

    def disconnect(self):
        if self.is_running:
            self.stop()

        self._clean()

    def _clean(self):
        if self.data_dir.exists():
            shutil.rmtree(self.data_dir)


class GethNetworkConfig(PluginConfig):
    # Make sure you are running the right networks when you try for these
    mainnet: dict = DEFAULT_SETTINGS.copy()
    goerli: dict = DEFAULT_SETTINGS.copy()
    # Make sure to run via `geth --dev` (or similar)
    local: dict = DEFAULT_SETTINGS.copy()


class NetworkConfig(PluginConfig):
    ethereum: GethNetworkConfig = GethNetworkConfig()

    class Config:
        extra = Extra.allow


class GethNotInstalledError(ConnectionError):
    def __init__(self):
        super().__init__(
            "geth is not installed and there is no local provider running.\n"
            "Things you can do:\n"
            "\t1. Install geth and try again\n"
            "\t2. Run geth separately and try again\n"
            "\t3. Use a different ape provider plugin"
        )


class BaseGethProvider(Web3Provider, ABC):
    _client_version: Optional[str] = None

    # optimal values for geth
    block_page_size = 5000
    concurrency = 16

    name: str = "geth"

    @property
    def uri(self) -> str:
        if "uri" in self.provider_settings:
            # Use adhoc, scripted value
            return self.provider_settings["uri"]

        config = self.config.dict().get(self.network.ecosystem.name, None)
        if config is None:
            return DEFAULT_SETTINGS["uri"]

        # Use value from config file
        network_config = config.get(self.network.name) or DEFAULT_SETTINGS
        return network_config.get("uri", DEFAULT_SETTINGS["uri"])

    @property
    def _clean_uri(self) -> str:
        return str(URL(self.uri).with_user(None).with_password(None))

    def _set_web3(self):
        self._client_version = None  # Clear cached version when connecting to another URI.
        self._web3 = _create_web3(self.uri)

    def _complete_connect(self):
        if "geth" in self.client_version.lower():
            self._log_connection("Geth")
        elif "erigon" in self.client_version.lower():
            self._log_connection("Erigon")
            self.concurrency = 8
            self.block_page_size = 40_000
        elif "nethermind" in self.client_version.lower():
            self._log_connection("Nethermind")
            self.concurrency = 32
            self.block_page_size = 50_000
        else:
            client_name = self.client_version.split("/")[0]
            logger.warning(f"Connecting Geth plugin to non-Geth client '{client_name}'.")

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

        try:
            block = self.web3.eth.get_block("latest")
        except ExtraDataLengthError:
            is_likely_poa = True
        else:
            is_likely_poa = (
                "proofOfAuthorityData" in block
                or len(block.get("extraData", "")) > MAX_EXTRADATA_LENGTH
            )

        if is_likely_poa:
            try:
                self.web3.middleware_onion.inject(geth_poa_middleware, layer=0)
            except ValueError as err:
                if "You can't add the same un-named instance twice" in str(err):
                    # Already added
                    pass
                else:
                    raise  # Original error

        self.network.verify_chain_id(chain_id)

    def disconnect(self):
        self._web3 = None
        self._client_version = None

    def get_transaction_trace(self, txn_hash: str) -> Iterator[TraceFrame]:
        frames = self._stream_request(
            "debug_traceTransaction", [txn_hash, {"enableMemory": True}], "result.structLogs.item"
        )
        for frame in frames:
            yield self._create_trace_frame(EvmTraceFrame(**frame))

    def _get_transaction_trace_using_call_tracer(self, txn_hash: str) -> Dict:
        return self._make_request(
            "debug_traceTransaction", [txn_hash, {"enableMemory": True, "tracer": "callTracer"}]
        )

    def get_call_tree(self, txn_hash: str) -> CallTreeNode:
        if "erigon" in self.client_version.lower():
            return self._get_parity_call_tree(txn_hash)

        try:
            # Try the Parity traces first, in case node client supports it.
            return self._get_parity_call_tree(txn_hash)
        except (ValueError, APINotImplementedError, ProviderError):
            return self._get_geth_call_tree(txn_hash)

    def _get_parity_call_tree(self, txn_hash: str) -> CallTreeNode:
        result = self._make_request("trace_transaction", [txn_hash])
        if not result:
            raise ProviderError(f"Failed to get trace for '{txn_hash}'.")

        traces = ParityTraceList.parse_obj(result)
        evm_call = get_calltree_from_parity_trace(traces)
        return self._create_call_tree_node(evm_call, txn_hash=txn_hash)

    def _get_geth_call_tree(self, txn_hash: str) -> CallTreeNode:
        calls = self._get_transaction_trace_using_call_tracer(txn_hash)
        evm_call = get_calltree_from_geth_call_trace(calls)
        return self._create_call_tree_node(evm_call, txn_hash=txn_hash)

    def _log_connection(self, client_name: str):
        logger.info(f"Connecting to existing {client_name} node at '{self._clean_uri}'.")

    def _make_request(self, endpoint: str, parameters: List) -> Any:
        try:
            return super()._make_request(endpoint, parameters)
        except ProviderError as err:
            if "does not exist/is not available" in str(err):
                raise APINotImplementedError(
                    f"RPC method '{endpoint}' is not implemented by this node instance."
                ) from err

            raise  # Original error

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


class GethDev(BaseGethProvider, TestProviderAPI):
    _process: Optional[GethDevProcess] = None
    name: str = "geth"

    @property
    def chain_id(self) -> int:
        return GETH_DEV_CHAIN_ID

    def __repr__(self):
        if self._process is None:
            # Exclude chain ID when not connected
            return "<geth>"

        return super().__repr__()

    def connect(self):
        self._set_web3()
        if not self.is_connected:
            self._start_geth()
        else:
            self._complete_connect()

    def _start_geth(self):
        test_config = self.config_manager.get_config("test").dict()
        process = GethDevProcess.from_uri(self.uri, self.data_folder, **test_config)
        process.connect()
        if not self.web3.is_connected():
            process.disconnect()
            raise ConnectionError("Unable to connect to locally running geth.")
        else:
            self.web3.middleware_onion.inject(geth_poa_middleware, layer=0)

        self._process = process

    def disconnect(self):
        # Must disconnect process first.
        if self._process is not None:
            self._process.disconnect()
            self._process = None

        super().disconnect()

    @raises_not_implemented
    def snapshot(self) -> SnapshotID:  # type: ignore[empty-body]
        # TODO: Replace with impl below after
        #  https://github.com/ethereum/go-ethereum/issues/26154 resolved
        pass

    def _snapshot(self) -> SnapshotID:
        return self.get_block("latest").number or 0

    @raises_not_implemented
    def revert(self, snapshot_id: SnapshotID):
        # TODO: Replace with impl below after
        #  https://github.com/ethereum/go-ethereum/issues/26154 resolved
        pass

    def _revert(self, snapshot_id: SnapshotID):
        if isinstance(snapshot_id, int):
            block_number_int = snapshot_id
            block_number_hex_str = str(to_hex(snapshot_id))
        elif isinstance(snapshot_id, bytes):
            block_number_hex_str = add_0x_prefix(HexStr(snapshot_id.hex()))
            block_number_int = int(block_number_hex_str, 16)
        else:
            block_number_hex_str = add_0x_prefix(HexStr(snapshot_id))
            block_number_int = int(snapshot_id, 16)

        current_block = self.get_block("latest").number
        if block_number_int == current_block:
            # Head is already at this block.
            return
        elif block_number_int > block_number_int:
            logger.error("Unable to set head to future block.")
            return

        self._make_request("debug_setHead", [block_number_hex_str])

    @raises_not_implemented
    def set_timestamp(self, new_timestamp: int):
        pass

    @raises_not_implemented
    def mine(self, num_blocks: int = 1):
        pass

    def send_call(self, txn: TransactionAPI, **kwargs: Any) -> bytes:
        skip_trace = kwargs.pop("skip_trace", False)
        arguments = self._prepare_call(txn, **kwargs)
        if skip_trace:
            return self._eth_call(arguments)

        show_gas = kwargs.pop("show_gas_report", False)
        show_trace = kwargs.pop("show_trace", False)
        track_gas = self.chain_manager._reports.track_gas
        needs_trace = show_gas or show_trace or track_gas
        if not needs_trace:
            return self._eth_call(arguments)

        # The user is requesting information related to a call's trace,
        # such as gas usage data.

        result = self._make_request("debug_traceCall", arguments)
        trace_data = result.get("structLogs", [])
        trace_frames = (EvmTraceFrame(**f) for f in trace_data)
        return_value = HexBytes(result["returnValue"])
        root_node_kwargs = {
            "gas_cost": result.get("gas", 0),
            "address": txn.receiver,
            "calldata": txn.data,
            "value": txn.value,
            "call_type": CallType.CALL,
            "failed": False,
            "returndata": return_value,
        }

        evm_call_tree = get_calltree_from_geth_trace(trace_frames, **root_node_kwargs)

        # NOTE: Don't pass txn_hash here, as it will fail (this is not a real txn).
        call_tree = self._create_call_tree_node(evm_call_tree)

        receiver = txn.receiver
        if track_gas and show_gas and not show_trace:
            # Optimization to enrich early and in_place=True.
            call_tree.enrich()

        if track_gas and call_tree and receiver is not None:
            # Gas report being collected, likely for showing a report
            # at the end of a test run.
            # Use `in_place=False` in case also `show_trace=True`
            enriched_call_tree = call_tree.enrich(in_place=False)
            self.chain_manager._reports.append_gas(enriched_call_tree, receiver)

        if show_gas:
            enriched_call_tree = call_tree.enrich(in_place=False)
            self.chain_manager._reports.show_gas(enriched_call_tree)

        if show_trace:
            call_tree = call_tree.enrich(use_symbol_for_tokens=True)
            self.chain_manager._reports.show_trace(call_tree)

        return return_value

    def get_call_tree(self, txn_hash: str, **root_node_kwargs) -> CallTreeNode:
        return self._get_geth_call_tree(txn_hash, **root_node_kwargs)


class Geth(BaseGethProvider, UpstreamProvider):
    @property
    def connection_str(self) -> str:
        return self.uri

    def connect(self):
        self._set_web3()
        if not self.is_connected:
            raise ProviderError(f"No node found on '{self._clean_uri}'.")

        self._complete_connect()


def _create_web3(uri: str):
    # Separated into helper method for testing purposes.
    provider = HTTPProvider(uri, request_kwargs={"timeout": 30 * 60})
    return Web3(provider)
