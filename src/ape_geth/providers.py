import shutil
from pathlib import Path
from typing import Any, Dict, Iterator, Optional, Union
from urllib.parse import urlparse

from eth_utils import to_wei
from evm_trace import (
    CallTreeNode,
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
from pydantic import Extra
from requests.exceptions import ConnectionError
from web3 import HTTPProvider, Web3
from web3.exceptions import ExtraDataLengthError
from web3.gas_strategies.rpc import rpc_gas_price_strategy
from web3.middleware import geth_poa_middleware
from web3.middleware.validation import MAX_EXTRADATA_LENGTH
from web3.types import RPCEndpoint

from ape.api import PluginConfig, UpstreamProvider, Web3Provider
from ape.api.networks import LOCAL_NETWORK_NAME
from ape.exceptions import ProviderError
from ape.logging import logger
from ape.utils import generate_dev_accounts

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
        number_of_accounts: int,
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
    ropsten: dict = DEFAULT_SETTINGS.copy()
    rinkeby: dict = DEFAULT_SETTINGS.copy()
    kovan: dict = DEFAULT_SETTINGS.copy()
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


class GethProvider(Web3Provider, UpstreamProvider):
    _geth: Optional[EphemeralGeth] = None
    _client_version: Optional[str] = None

    @property
    def uri(self) -> str:
        ecosystem_config = self.config.dict().get(self.network.ecosystem.name, None)
        if ecosystem_config is None:
            return DEFAULT_SETTINGS["uri"]

        network_config = ecosystem_config.get(self.network.name)
        return network_config.get("uri", DEFAULT_SETTINGS["uri"])

    @property
    def connection_str(self) -> str:
        return self.uri

    @property
    def client_version(self) -> str:
        if not self._web3:
            return ""

        # NOTE: Gets reset to `None` on `connect()` and `disconnect()`.
        if self._client_version is None:
            self._client_version = self._web3.clientVersion

        return self._client_version

    def connect(self):
        self._client_version = None  # Clear cached version when connecting to another URI.
        self._web3 = Web3(HTTPProvider(self.uri))

        if not self._web3.isConnected():
            if self.network.name != LOCAL_NETWORK_NAME:
                raise ProviderError(
                    f"When running on network '{self.network.name}', "
                    f"the Geth plugin expects the Geth process to already "
                    f"be running on '{self.uri}'."
                )

            # Start an ephemeral geth process.
            parsed_uri = urlparse(self.uri)

            if parsed_uri.hostname not in ("localhost", "127.0.0.1"):
                raise ConnectionError(f"Unable to connect web3 to {parsed_uri.hostname}.")

            if not shutil.which("geth"):
                raise GethNotInstalledError()

            # Use mnemonic from test config
            config_manager = self.network.config_manager
            test_config = config_manager.get_config("test")
            mnemonic = test_config["mnemonic"]
            num_of_accounts = test_config["number_of_accounts"]

            self._geth = EphemeralGeth(
                self.data_folder,
                parsed_uri.hostname,
                parsed_uri.port,
                mnemonic,
                number_of_accounts=num_of_accounts,
            )
            self._geth.connect()

            if not self._web3.isConnected():
                self._geth.disconnect()
                raise ConnectionError("Unable to connect to locally running geth.")
        else:
            if "geth" in self.client_version.lower():
                logger.info(f"Connecting to existing Geth node at '{self.uri}'.")
            else:
                network_name = self.client_version.split("/")[0]
                logger.warning(f"Connecting Geth plugin to non-Geth network '{network_name}'.")

        self._web3.eth.set_gas_price_strategy(rpc_gas_price_strategy)

        def is_likely_poa() -> bool:
            try:
                block = self.web3.eth.get_block("latest")
            except ExtraDataLengthError:
                return True

            return (
                "proofOfAuthorityData" in block
                or len(block.get("extraData", "")) > MAX_EXTRADATA_LENGTH
            )

        # If network is rinkeby, goerli, or kovan (PoA test-nets)
        if self._web3.eth.chain_id in (4, 5, 42) or is_likely_poa():
            self._web3.middleware_onion.inject(geth_poa_middleware, layer=0)

        if self.network.name != LOCAL_NETWORK_NAME and self.network.chain_id != self.chain_id:
            raise ProviderError(
                "HTTP Connection does not match expected chain ID. "
                f"Are you connected to '{self.network.name}'?"
            )

    def disconnect(self):
        if self._geth is not None:
            self._geth.disconnect()
            self._geth = None

        # Must happen after geth.disconnect()
        self._web3 = None  # type: ignore
        self._client_version = None

    def get_transaction_trace(self, txn_hash: str) -> Iterator[TraceFrame]:
        frames = self._make_request("debug_traceTransaction", [txn_hash]).structLogs
        for frame in frames:
            yield TraceFrame(**frame)

    def get_call_tree(self, txn_hash: str, **root_node_kwargs) -> CallTreeNode:
        def _get_call_tree_from_parity():
            data = self._make_request("trace_transaction", [txn_hash])
            traces = ParityTraceList.parse_obj(data)
            return get_calltree_from_parity_trace(traces)

        if "erigon" in self.client_version.lower():
            return _get_call_tree_from_parity()

        try:
            # Try the Parity traces first just in case
            return _get_call_tree_from_parity()
        except ValueError:
            frames = self.get_transaction_trace(txn_hash)
            return get_calltree_from_geth_trace(frames, **root_node_kwargs)

    def _make_request(self, rpc: str, args: list) -> Any:
        endpoint = RPCEndpoint(rpc)
        return self.web3.manager.request_blocking(endpoint, args)  # type: ignore
