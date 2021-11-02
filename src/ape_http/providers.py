import shutil
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional, Union
from urllib.parse import urlparse

from eth_typing import HexStr
from geth import DevGethProcess, LoggingMixin  # type: ignore
from requests.exceptions import ConnectionError
from requests.exceptions import ConnectionError as RequestsConnectionError
from web3 import HTTPProvider, Web3
from web3.exceptions import ContractLogicError as Web3ContractLogicError
from web3.gas_strategies.rpc import rpc_gas_price_strategy
from web3.middleware import geth_poa_middleware
from web3.types import NodeInfo, RPCEndpoint

from ape.api import ReceiptAPI, TransactionAPI
from ape.api.config import ConfigItem
from ape.api.providers import TestProviderAPI
from ape.exceptions import (
    ContractLogicError,
    OutOfGasError,
    ProviderError,
    RPCError,
    TransactionError,
    VirtualMachineError,
)
from ape.logging import logger
from ape.utils import (
    extract_nested_value,
    generate_dev_accounts,
    get_gas_estimation_revert_error_message,
)

DEFAULT_SETTINGS = {"uri": "http://localhost:8545", "chain_name": "devchain"}


class EphemeralGeth(LoggingMixin, DevGethProcess):
    """
    A developer-configured geth that only exists until disconnected.
    """

    def __init__(
        self,
        chain_name,
        base_directory: Path,
        hostname: str,
        port: int,
        chain_id: int = 1337,
        initial_balance: Union[str, int] = "10000000000000000000000",
        accounts: List = None,
    ):
        self.data_dir = base_directory / chain_name
        self._hostname = hostname
        self._port = port

        accounts = accounts or generate_dev_accounts()
        genesis_data: Dict = {
            "coinbase": "0x0000000000000000000000000000000000000000",
            "difficulty": "0x0",
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
                "ethash": {},
            },
            "alloc": {a.address: {"balance": str(initial_balance)} for a in accounts},
        }
        geth_cmd_args = {
            "rpc_addr": hostname,
            "rpc_port": str(port),
            "network_id": str(chain_id),
            "allow_insecure_unlock": True,
        }

        def make_logs_paths(stream_name: str):
            path = base_directory / "geth-logs" / f"{stream_name}_{self._port}"
            path.parent.mkdir(exist_ok=True, parents=True)
            return path

        super().__init__(
            chain_name,
            base_dir=base_directory,
            overrides=geth_cmd_args,
            genesis_data=genesis_data,
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

        # Convert data dir back to Path from base class.
        data_dir = Path(str(self.data_dir))

        # Clean up blockchain
        if data_dir.exists():
            shutil.rmtree(self.data_dir)


class EthereumNetworkConfig(ConfigItem):
    # Make sure you are running the right networks when you try for these
    mainnet: dict = DEFAULT_SETTINGS.copy()
    ropsten: dict = DEFAULT_SETTINGS.copy()
    rinkeby: dict = DEFAULT_SETTINGS.copy()
    kovan: dict = DEFAULT_SETTINGS.copy()
    goerli: dict = DEFAULT_SETTINGS.copy()
    # Make sure to run via `geth --dev` (or similar)
    development: dict = DEFAULT_SETTINGS.copy()


class NetworkConfig(ConfigItem):
    ethereum: EthereumNetworkConfig = EthereumNetworkConfig()


class GethNotInstalledError(ConnectionError):
    def __init__(self):
        super().__init__(
            "geth is not installed and there is no local provider running.\n"
            "Your options are:\n"
            "\t1. Install geth and try again\n"
            "\t2. use a different ape provider plugin\n"
            "\t3. run a local blockchain separately\n\n"
            "Also make sure you to configure the URI in `ape-config.yaml` "
            "if it is not standard.\n"
            "Also note that the HTTP provider is only meant to support geth."
        )


class EthereumProvider(TestProviderAPI):
    _web3: Web3 = None  # type: ignore
    _geth: Optional[EphemeralGeth] = None

    @property
    def uri(self) -> str:
        return self._get_setting("uri")

    @property
    def _chain_name(self) -> str:
        return self._get_setting("chain_name")

    def _get_setting(self, key: str) -> Any:
        given_settings = self.provider_settings or {}
        config_settings = getattr(self.config, self.network.ecosystem.name)[self.network.name]
        return given_settings.get(key) or config_settings.get(key)

    def connect(self):
        self._web3 = Web3(HTTPProvider(self.uri))

        # Try to start an ephemeral geth process if no provider is running.
        if not self._web3.isConnected():
            parsed_uri = urlparse(self.uri)

            if parsed_uri.hostname not in ("localhost", "127.0.0.1"):
                raise ConnectionError(f"Unable to connect web3 to {parsed_uri.hostname}")

            if not shutil.which("geth"):
                raise GethNotInstalledError()

            self._geth = EphemeralGeth(
                self._chain_name, self.data_folder, parsed_uri.hostname, parsed_uri.port
            )
            self._geth.connect()

            if not self._web3.isConnected():
                self._geth.disconnect()
                raise ConnectionError("Unable to connect to locally running geth.")

        self._web3.eth.set_gas_price_strategy(rpc_gas_price_strategy)

        # Try to detect if chain used clique (PoA).
        node_info = self._node_info or {}
        chain_config = extract_nested_value(node_info, "protocols", "eth", "config")
        is_poa_chain = chain_config is not None and "clique" in chain_config

        # If network is rinkeby, goerli, or kovan (PoA test-nets)
        if self._web3.eth.chain_id in (4, 5, 42) or is_poa_chain:
            self._web3.middleware_onion.inject(geth_poa_middleware, layer=0)

        if self.network.name != "development" and self.network.chain_id != self.chain_id:
            raise ProviderError(
                "HTTP Connection does not match expected chain ID. "
                f"Are you connected to '{self.network.name}'?"
            )

    def disconnect(self):
        if self._geth is not None:
            self._geth.disconnect()
            self._geth = None

        # This must happen after geth.disconnect()
        self._web3 = None  # type: ignore

    def update_settings(self, new_settings: dict):
        self.disconnect()
        self.provider_settings.update(new_settings)
        self.connect()

    def estimate_gas_cost(self, txn: TransactionAPI) -> int:
        """
        Generates and returns an estimate of how much gas is necessary
        to allow the transaction to complete.
        The transaction will not be added to the blockchain.
        """
        try:
            txn_dict = txn.as_dict()
            return self._web3.eth.estimate_gas(txn_dict)  # type: ignore
        except ValueError as err:
            tx_error = _get_vm_error(err)

            # If this is the cause of a would-be revert,
            # raise ContractLogicError so that we can confirm tx-reverts.
            if isinstance(tx_error, ContractLogicError):
                raise tx_error from err

            message = get_gas_estimation_revert_error_message(tx_error)
            raise TransactionError(base_err=tx_error, message=message) from err

    @property
    def chain_id(self) -> int:
        """
        Returns the currently configured chain ID,
        a value used in replay-protected transaction signing as introduced by EIP-155.
        """
        return self._web3.eth.chain_id

    @property
    def gas_price(self):
        """
        Returns the current price per gas in wei.
        """
        return self._web3.eth.generate_gas_price()

    @property
    def _node_info(self) -> Optional[NodeInfo]:
        try:
            return self._web3.geth.admin.node_info()
        except ValueError:
            return None

    def get_nonce(self, address: str) -> int:
        """
        Returns the number of transactions sent from an address.
        """
        return self._web3.eth.get_transaction_count(address)  # type: ignore

    def get_balance(self, address: str) -> int:
        """
        Returns the balance of the account of a given address.
        """
        return self._web3.eth.get_balance(address)  # type: ignore

    def get_code(self, address: str) -> bytes:
        """
        Returns code at a given address.
        """
        return self._web3.eth.get_code(address)  # type: ignore

    def send_call(self, txn: TransactionAPI) -> bytes:
        """
        Executes a new message call immediately without creating a
        transaction on the block chain.
        """
        return self._web3.eth.call(txn.as_dict())

    def get_transaction(self, txn_hash: str) -> ReceiptAPI:
        """
        Returns the information about a transaction requested by transaction hash.
        """
        # TODO: Work on API that let's you work with ReceiptAPI and re-send transactions
        receipt = self._web3.eth.wait_for_transaction_receipt(txn_hash)  # type: ignore
        txn = self._web3.eth.get_transaction(txn_hash)  # type: ignore
        return self.network.ecosystem.receipt_class.decode({**txn, **receipt})

    def send_transaction(self, txn: TransactionAPI) -> ReceiptAPI:
        """
        Creates a new message call transaction or a contract creation
        for signed transactions.
        """
        try:
            txn_hash = self._web3.eth.send_raw_transaction(txn.encode())
        except ValueError as err:
            raise _get_vm_error(err) from err

        receipt = self.get_transaction(txn_hash.hex())

        if txn.gas_limit is not None and receipt.ran_out_of_gas(txn.gas_limit):
            raise OutOfGasError()

        return receipt

    def get_events(self, **filter_params) -> Iterator[dict]:
        """
        Returns an array of all logs matching a given set of filter parameters.
        """
        return iter(self._web3.eth.get_logs(filter_params))  # type: ignore

    def snapshot(self) -> Dict:
        raise NotImplementedError()

    def revert(self, snapshot_id: Dict):
        raise NotImplementedError()

    def set_head(self, block_number: str):
        block_number = HexStr(block_number)
        self._make_request("debug_setHead", args=[block_number])

    def _make_request(self, method: str, args: List) -> Optional[Any]:
        try:
            response = self._web3.provider.make_request(RPCEndpoint(method), args)
        except (AttributeError, RequestsConnectionError) as err:
            raise RPCError(f"web3 is not connected.\nErr: {err}.") from err

        if not response:
            raise RPCError(f"Unable to make request {method}")

        error_data = response.get("error")
        if error_data:
            error_message = (
                error_data.get("message", error_data)
                if isinstance(error_data, dict)
                else error_data
            )
            raise RPCError(error_message)

        return response.get("result")


def _get_vm_error(web3_value_error: ValueError) -> TransactionError:
    """
    Returns a custom error from ``ValueError`` from web3.py.
    """
    if isinstance(web3_value_error, Web3ContractLogicError):
        # This happens from `assert` or `require` statements.
        message = str(web3_value_error).split(":")[-1].strip()
        return ContractLogicError(message)

    if not len(web3_value_error.args):
        return VirtualMachineError(web3_value_error)

    err_data = web3_value_error.args[0]
    if not isinstance(err_data, dict):
        return VirtualMachineError(web3_value_error)

    message = str(err_data.get("message"))
    if not message:
        return VirtualMachineError(web3_value_error)

    return VirtualMachineError(message=message, code=err_data.get("code"))
