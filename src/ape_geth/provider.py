import shutil
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional, Union

import ijson  # type: ignore
import requests
from eth_typing import HexStr
from eth_utils import to_wei, to_hex, add_0x_prefix

from ape.types import SnapshotID
from evm_trace import (
    CallTreeNode,
    CallType,
    ParityTraceList,
    TraceFrame,
    get_calltree_from_geth_trace,
    get_calltree_from_parity_trace,
)
from geth import LoggingMixin  # type: ignore
from geth.accounts import ensure_account_exists  # type: ignore
from geth.chain import initialize_chain  # type: ignore
from geth.process import BaseGethProcess  # type: ignore
from geth.wrapper import construct_test_chain_kwargs  # type: ignore
from pydantic import Extra, PositiveInt
from requests.exceptions import ConnectionError
from web3 import HTTPProvider, Web3
from web3.exceptions import ExtraDataLengthError
from web3.gas_strategies.rpc import rpc_gas_price_strategy
from web3.middleware import geth_poa_middleware
from web3.middleware.validation import MAX_EXTRADATA_LENGTH
from yarl import URL

from ape.api import PluginConfig, UpstreamProvider, Web3Provider, TestProviderAPI
from ape.exceptions import APINotImplementedError, ProviderError
from ape.logging import logger
from ape.utils import generate_dev_accounts, raises_not_implemented

DEFAULT_SETTINGS = {"uri": "http://localhost:8545"}


class EphemeralGeth(LoggingMixin, BaseGethProcess):
    """
    A developer-configured geth that only exists until disconnected.
    """

    def __init__(
        self,
        base_directory: Path,
        hostname: str,
        port: int,
        mnemonic: str,
        number_of_accounts: PositiveInt,
        chain_id: int = 1337,
        initial_balance: Union[str, int] = to_wei(10000, "ether"),
    ):
        self.data_dir = base_directory / "dev"
        self._hostname = hostname
        self._port = port
        geth_kwargs = construct_test_chain_kwargs(
            data_dir=self.data_dir,
            rpc_addr=hostname,
            rpc_port=port,
            network_id=chain_id,
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


class BaseGethProvider(Web3Provider):
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
        network_config = config.get(self.network.name)
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

        self._web3.eth.set_gas_price_strategy(rpc_gas_price_strategy)

        # Check for chain errors, including syncing
        try:
            chain_id = self._web3.eth.chain_id
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
            self._web3.middleware_onion.inject(geth_poa_middleware, layer=0)

        self.network.verify_chain_id(chain_id)

    def disconnect(self):
        self._web3 = None
        self._client_version = None

    def get_transaction_trace(self, txn_hash: str) -> Iterator[TraceFrame]:
        frames = self._stream_request(
            "debug_traceTransaction", [txn_hash, {"enableMemory": True}], "result.structLogs.item"
        )
        for frame in frames:
            yield TraceFrame(**frame)

    def get_call_tree(self, txn_hash: str, **root_node_kwargs) -> CallTreeNode:
        def _get_call_tree_from_parity():
            result = self._make_request("trace_transaction", [txn_hash])
            if not result:
                raise ProviderError(f"Failed to get trace for '{txn_hash}'.")

            traces = ParityTraceList.parse_obj(result)
            return get_calltree_from_parity_trace(traces)

        if "erigon" in self.client_version.lower():
            return _get_call_tree_from_parity()

        try:
            # Try the Parity traces first, in case node client supports it.
            return _get_call_tree_from_parity()
        except (ValueError, APINotImplementedError, ProviderError):
            if not root_node_kwargs:
                receipt = self.get_receipt(txn_hash)

                if not receipt.receiver:
                    raise ProviderError("Receipt missing receiver.")

                root_node_kwargs = {
                    "gas_cost": receipt.gas_used,
                    "gas_limit": receipt.gas_limit,
                    "address": receipt.receiver,
                    "calldata": receipt.data,
                    "value": receipt.value,
                    "call_type": CallType.CALL,
                    "failed": receipt.failed,
                }

            frames = self.get_transaction_trace(txn_hash)
            return get_calltree_from_geth_trace(frames, **root_node_kwargs)

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


class GethDev(TestProviderAPI, BaseGethProvider):
    _geth: Optional[EphemeralGeth] = None
    name: str = "geth"

    def connect(self):
        self._set_web3()
        if not self.is_connected:
            self._start_geth()
        else:
            self._complete_connect()

    def _start_geth(self):
        parsed_uri = URL(self.uri)

        if parsed_uri.host not in ("localhost", "127.0.0.1"):
            raise ConnectionError(f"Unable to connect web3 to {parsed_uri.host}.")

        if not shutil.which("geth"):
            raise GethNotInstalledError()

        # Use mnemonic from test config
        config_manager = self.network.config_manager
        test_config = config_manager.get_config("test")
        mnemonic = test_config["mnemonic"]
        num_of_accounts = test_config["number_of_accounts"]

        self._geth = EphemeralGeth(
            self.data_folder,
            parsed_uri.host,
            parsed_uri.port,
            mnemonic,
            number_of_accounts=num_of_accounts,
        )
        self._geth.connect()
        if not self._web3.is_connected():
            self._geth.disconnect()
            raise ConnectionError("Unable to connect to locally running geth.")
        else:
            self._web3.middleware_onion.inject(geth_poa_middleware, layer=0)

    def disconnect(self):
        # Must disconnect process first.
        if self._geth is not None:
            self._geth.disconnect()
            self._geth = None

        super().disconnect()

    def revert(self, snapshot_id: SnapshotID):
        if isinstance(snapshot_id, int):
            block_number = to_hex(snapshot_id)
        elif isinstance(snapshot_id, bytes):
            block_number = add_0x_prefix(HexStr(snapshot_id.hex()))
        else:
            block_number = str(snapshot_id)

        self._make_request("debug_setHead", [block_number])

    def snapshot(self) -> SnapshotID:
        return self.get_block("latest").number

    @raises_not_implemented
    def set_timestamp(self, new_timestamp: int):
        pass

    @raises_not_implemented
    def mine(self, num_blocks: int = 1):
        pass


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
