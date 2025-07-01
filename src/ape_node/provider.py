import atexit
import os.path
import re
import shutil
from pathlib import Path
from subprocess import DEVNULL, PIPE, Popen
from typing import TYPE_CHECKING, Any, Optional, Union
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import urlopen

from eth_utils import add_0x_prefix, to_hex
from geth.chain import initialize_chain as initialize_gethdev_chain
from geth.process import BaseGethProcess
from geth.wrapper import ALL_APIS, construct_test_chain_kwargs
from pydantic import field_validator
from pydantic_settings import SettingsConfigDict
from requests.exceptions import ConnectionError

from ape.api.config import PluginConfig
from ape.api.providers import SubprocessProvider, TestProviderAPI
from ape.exceptions import VirtualMachineError
from ape.logging import LogLevel, logger
from ape.utils._web3_compat import ExtraDataToPOAMiddleware
from ape.utils.misc import ZERO_ADDRESS, log_instead_of_fail, raises_not_implemented
from ape.utils.process import JoinableQueue, spawn
from ape.utils.testing import (
    DEFAULT_NUMBER_OF_TEST_ACCOUNTS,
    DEFAULT_TEST_ACCOUNT_BALANCE,
    DEFAULT_TEST_CHAIN_ID,
    DEFAULT_TEST_HD_PATH,
    DEFAULT_TEST_MNEMONIC,
    generate_dev_accounts,
)
from ape_ethereum.provider import (
    DEFAULT_HOSTNAME,
    DEFAULT_PORT,
    DEFAULT_SETTINGS,
    EthereumNodeProvider,
)
from ape_ethereum.trace import TraceApproach

if TYPE_CHECKING:
    from geth.types import GenesisDataTypedDict

    from ape.api.accounts import TestAccountAPI
    from ape.api.transactions import ReceiptAPI, TransactionAPI
    from ape.types.vm import SnapshotID


Alloc = dict[str, dict[str, Any]]


def create_genesis_data(alloc: Alloc, chain_id: int) -> "GenesisDataTypedDict":
    """
    A wrapper around genesis data for py-geth that
    fills in more defaults.
    """
    return {
        "alloc": alloc,
        "config": {
            "arrowGlacierBlock": 0,
            "berlinBlock": 0,
            "byzantiumBlock": 0,
            "cancunTime": 0,
            "chainId": chain_id,
            "constantinopleBlock": 0,
            "daoForkBlock": 0,
            "daoForkSupport": True,
            "eip150Block": 0,
            "eip155Block": 0,
            "eip158Block": 0,
            "ethash": {},
            "grayGlacierBlock": 0,
            "homesteadBlock": 0,
            "istanbulBlock": 0,
            "londonBlock": 0,
            "petersburgBlock": 0,
            "shanghaiTime": 0,
            "terminalTotalDifficulty": 0,
            "terminalTotalDifficultyPassed": True,
            "blobSchedule": {
                "cancun": {"target": 3, "max": 6, "baseFeeUpdateFraction": 3338477},
                "prague": {"target": 6, "max": 9, "baseFeeUpdateFraction": 5007716},
            },
        },
        "coinbase": ZERO_ADDRESS,
        "difficulty": "0x0",
        "gasLimit": "0x0",
        "extraData": "0x",
        "mixHash": "0x0000000000000000000000000000000000000000000000000000000000000000",
        "nonce": "0x0",
        "timestamp": "0x0",
        "parentHash": "0x0000000000000000000000000000000000000000000000000000000000000000",
        "baseFeePerGas": "0x0",
    }


def get_node_name_from_executable(executable: str) -> str:
    return executable.split(os.path.sep)[-1] or "geth"


class GethDevProcess(BaseGethProcess):
    """
    A developer-configured geth that only exists until disconnected.
    (Implementation detail of the local node provider).
    """

    def __init__(
        self,
        data_dir: Path,
        hostname: Optional[str] = None,
        port: Optional[int] = None,
        ipc_path: Optional[Path] = None,
        ws_hostname: Optional[str] = None,
        ws_port: Optional[str] = None,
        mnemonic: str = DEFAULT_TEST_MNEMONIC,
        number_of_accounts: int = DEFAULT_NUMBER_OF_TEST_ACCOUNTS,
        chain_id: int = DEFAULT_TEST_CHAIN_ID,
        initial_balance: Union[str, int] = DEFAULT_TEST_ACCOUNT_BALANCE,
        executable: Optional[Union[list[str], str]] = None,
        auto_disconnect: bool = True,
        extra_funded_accounts: Optional[list[str]] = None,
        hd_path: Optional[str] = DEFAULT_TEST_HD_PATH,
        block_time: Optional[int] = None,
        generate_accounts: bool = True,
        initialize_chain: bool = True,
        background: bool = False,
        verify_bin: bool = True,
        rpc_api: Optional[list[str]] = None,
    ):
        if isinstance(executable, str):
            # Legacy.
            executable = [executable]

        if executable:
            if verify_bin and (
                not Path(executable[0]).exists() and not shutil.which(executable[0])
            ):
                raise NodeSoftwareNotInstalledError()

        else:
            # Executable not specified: attempt to find one in $PATH.
            if shutil.which("geth"):
                executable = ["geth"]
            elif shutil.which("reth"):
                executable = ["reth", "node"]
            elif verify_bin:
                # TODO: Add support for more nodes, such as erigon.
                raise NodeSoftwareNotInstalledError()
            else:
                # This probably won't work if started, but the user knows that.
                executable = ["geth"]

        self.executable = executable or ["geth"]
        self._data_dir = data_dir
        self.is_running = False
        self._auto_disconnect = auto_disconnect
        self.background = background

        is_reth = executable[0].endswith("reth")

        if is_reth and hostname == "localhost":
            # Reth only supports IP format.
            hostname = "127.0.0.1"

        kwargs_ctor: dict = {
            "data_dir": self.data_dir,
            "geth_executable": executable[0],
            "network_id": f"{chain_id}",
        }
        if hostname is not None:
            kwargs_ctor["rpc_addr"] = hostname
        if port is not None:
            kwargs_ctor["rpc_port"] = f"{port}"
        if ws_hostname:
            kwargs_ctor["ws_enabled"] = True
            kwargs_ctor["ws_addr"] = ws_hostname
        if ws_port:
            kwargs_ctor["ws_enabled"] = True
            kwargs_ctor["ws_port"] = f"{ws_port}"
        if ipc_path is not None:
            kwargs_ctor["ipc_path"] = f"{ipc_path}"
        if not kwargs_ctor.get("ws_enabled"):
            kwargs_ctor["ws_api"] = None
            kwargs_ctor["ws_enabled"] = False
            kwargs_ctor["ws_addr"] = None
            kwargs_ctor["ws_port"] = None
        if block_time is not None and not is_reth:
            kwargs_ctor["dev_period"] = f"{block_time}"

        if rpc_api is None:
            # Reth also has MEV API support.
            rpc_api_str = f"{ALL_APIS},mev" if is_reth else ALL_APIS
        else:
            rpc_api_str = ",".join(rpc_api)

        kwargs_ctor["rpc_api"] = rpc_api_str
        geth_kwargs = construct_test_chain_kwargs(**kwargs_ctor)
        if is_reth:
            geth_kwargs.pop("max_peers", None)
            geth_kwargs.pop("network_id", None)
            geth_kwargs.pop("no_discover", None)

            # NOTE: --verbosity _is_ available in reth, but it is a different type (flag only).
            #   It isn't really needed anyway (I don't think).
            geth_kwargs.pop("verbosity", None)

            geth_kwargs.pop("password", None)

        # Ensure IPC path has correct name.
        if ipc_path_kwarg := geth_kwargs.get("ipc_path"):
            if ipc_path_kwarg.endswith("geth.ipc"):
                geth_kwargs["ipc_path"] = ipc_path_kwarg.replace(
                    "geth.ipc", f"{self.process_name}.ipc"
                )

        # Ensure a clean data-dir.
        self._clean()

        geth_kwargs["dev_mode"] = True
        hd_path = hd_path or DEFAULT_TEST_HD_PATH

        if generate_accounts:
            self._dev_accounts = generate_dev_accounts(
                mnemonic, number_of_accounts=number_of_accounts, hd_path=hd_path
            )
        else:
            self._dev_accounts = []

        if initialize_chain:
            addresses = [a.address for a in self._dev_accounts]
            addresses.extend(extra_funded_accounts or [])
            bal_dict = {"balance": str(initial_balance)}
            alloc = dict.fromkeys(addresses, bal_dict)
            genesis = create_genesis_data(alloc, chain_id)
            self._data_dir.mkdir(parents=True, exist_ok=True)
            initialize_gethdev_chain(genesis, self.data_dir)

        super().__init__(geth_kwargs)

        # Correct multi-word executable.
        idx = self.command.index(executable[0])
        self.command = self.command[:idx] + executable + self.command[idx + 1 :]

    @classmethod
    def from_uri(cls, uri: str, data_folder: Path, **kwargs):
        mnemonic = kwargs.get("mnemonic", DEFAULT_TEST_MNEMONIC)
        number_of_accounts = kwargs.get("number_of_accounts", DEFAULT_NUMBER_OF_TEST_ACCOUNTS)
        balance = kwargs.get("initial_balance", DEFAULT_TEST_ACCOUNT_BALANCE)
        extra_accounts = [a.lower() for a in kwargs.get("extra_funded_accounts", [])]
        block_time = kwargs.get("block_time", None)
        if isinstance(block_time, int):
            block_time = f"{block_time}"

        executable = kwargs.get("executable")

        process_kwargs = {
            "auto_disconnect": kwargs.get("auto_disconnect", True),
            "background": kwargs.get("background", False),
            "block_time": block_time,
            "executable": executable,
            "extra_funded_accounts": extra_accounts,
            "hd_path": kwargs.get("hd_path", DEFAULT_TEST_HD_PATH),
            "initial_balance": balance,
            "mnemonic": mnemonic,
            "number_of_accounts": number_of_accounts,
            "verify_bin": kwargs.get("verify_bin", True),
        }

        parsed_uri = urlparse(uri)
        if not parsed_uri.netloc:
            path = Path(parsed_uri.path)
            if path.suffix == ".ipc":
                # Was given an IPC path.
                process_kwargs["ipc_path"] = path

            else:
                raise ConnectionError(f"Unrecognized path type: '{path}'.")

        elif hostname := parsed_uri.hostname:
            if hostname not in ("localhost", "127.0.0.1"):
                name = get_node_name_from_executable(executable) if executable else "geth"
                raise ConnectionError(
                    f"Unable to start {name} on non-local host {parsed_uri.hostname}."
                )

            if parsed_uri.scheme.startswith("ws"):
                process_kwargs["ws_hostname"] = hostname
                process_kwargs["ws_port"] = parsed_uri.port or DEFAULT_PORT
            elif parsed_uri.scheme.startswith("http"):
                process_kwargs["hostname"] = hostname or DEFAULT_HOSTNAME
                process_kwargs["port"] = parsed_uri.port or DEFAULT_PORT
            else:
                raise ConnectionError(f"Unsupported scheme: '{parsed_uri.scheme}'.")

        return cls(data_folder, **process_kwargs)

    @property
    def data_dir(self) -> str:
        return f"{self._data_dir}"

    @property
    def process_name(self) -> str:
        return get_node_name_from_executable(self.executable[0])

    @property
    def ipc_path(self) -> str:
        # Overridden: so we can use a custom IPC path name (e.g. reth.ipc).
        return self.geth_kwargs.get("ipc_path") or os.path.abspath(
            os.path.expanduser(
                os.path.join(
                    self.data_dir,
                    f"{self.process_name}.ipc",
                )
            )
        )

    @property
    def is_rpc_ready(self) -> bool:
        # Overridden: This is overridden to work with other nodes besides `geth`.
        #   Otherwise, the RPC is never declared as ready even though it is.
        try:
            urlopen(f"http://{self.rpc_host}:{self.rpc_port}")

        except HTTPError:
            # Reth nodes (and maybe others) might throw an HTTP error here, like "method not found".
            # This means the RPC is ready.
            return True

        except URLError:
            # Nothing found at all yet, most likely.
            return False

        else:
            # No error occurs on Geth nodes when the RPC is ready.
            return True

    @property
    def _hostname(self) -> Optional[str]:
        return self.geth_kwargs.get("rpc_addr")

    @property
    def _port(self) -> Optional[str]:
        return self.geth_kwargs.get("rpc_port")

    @property
    def _ws_hostname(self) -> Optional[str]:
        return self.geth_kwargs.get("ws_addr")

    @property
    def _ws_port(self) -> Optional[str]:
        return self.geth_kwargs.get("ws_port")

    def connect(self, timeout: int = 60):
        self._log_connection()
        self.start()
        self.wait_for_rpc(timeout=timeout)

        # Register atexit handler to make sure disconnect is called for normal object lifecycle.
        if self._auto_disconnect:
            atexit.register(self.disconnect)

    def _log_connection(self):
        home = str(Path.home())
        ipc_path = self.ipc_path.replace(home, "$HOME")

        http_log = ""
        if self._hostname:
            http_log = f"HTTP={self._hostname}"
            if port := self._port:
                http_log = f"{http_log}:{port}"

        ipc_log = f"IPC={ipc_path}"

        ws_log = ""
        if self._ws_hostname:
            ws_log = f"WS={self._ws_hostname}"
            if port := self._ws_port:
                ws_log = f"{ws_log}:{port}"

        connection_logs = ", ".join(x for x in (http_log, ipc_log, ws_log) if x)
        logger.info(f"Starting {self.process_name} ({connection_logs}).")

    def start(self):
        if self.is_running:
            return

        self.is_running = True

        if self.background or logger.level > LogLevel.DEBUG:
            out_file = DEVNULL
        else:
            out_file = PIPE

        self.proc = Popen(
            self.command,
            stdin=PIPE,
            stdout=out_file,
            stderr=out_file,
        )

    def disconnect(self):
        if self.is_running:
            logger.info(f"Stopping '{self.process_name}' process.")
            self.stop()

        self._clean()

    def _clean(self):
        if self._data_dir.is_dir():
            shutil.rmtree(self._data_dir)

    def wait(self, *args, **kwargs):
        if self.proc is None:
            return

        self.proc.wait(*args, **kwargs)


class EthereumNetworkConfig(PluginConfig):
    # Make sure you are running the right networks when you try for these
    mainnet: dict = {}
    holesky: dict = {}
    sepolia: dict = {}
    # Make sure to run via `geth --dev` (or similar)
    local: dict = {**DEFAULT_SETTINGS.copy(), "chain_id": DEFAULT_TEST_CHAIN_ID, "block_time": 0}

    model_config = SettingsConfigDict(extra="allow", env_prefix="APE_NODE_")

    @field_validator("local", mode="before")
    @classmethod
    def _validate_local(cls, value):
        value = value or {}
        if not value:
            return {**DEFAULT_SETTINGS.copy(), "chain_id": DEFAULT_TEST_CHAIN_ID}

        if "chain_id" not in value:
            value["chain_id"] = DEFAULT_TEST_CHAIN_ID
        if ("uri" not in value and "ipc_path" in value) or "ws_uri" in value or "http_uri" in value:
            # No need to add default HTTP URI if was given only IPC Path
            return {**{k: v for k, v in DEFAULT_SETTINGS.items() if k != "uri"}, **value}

        return {**DEFAULT_SETTINGS, **value}


class EthereumNodeConfig(PluginConfig):
    """
    Configure your ``node:`` in Ape, the default provider
    plugin for live-network nodes. Also, ``ape node`` can
    start-up a local development node for testing purposes.
    """

    ethereum: EthereumNetworkConfig = EthereumNetworkConfig()
    """
    Configure the Ethereum network settings for the ``ape node`` provider,
    such as which URIs to use for each network.
    """

    executable: Optional[list[str]] = None
    """
    For starting nodes, select the executable. Defaults to using
    ``shutil.which("geth")``.
    """

    data_dir: Optional[Path] = None
    """
    For node-management, choose where the geth data directory shall
    be located. Defaults to using a location within Ape's DATA_FOLDER.
    """

    ipc_path: Optional[Path] = None
    """
    For IPC connections, select the IPC path. If managing a process,
    web3.py can determine the IPC w/o needing to manually configure.
    """

    call_trace_approach: Optional[TraceApproach] = None
    """
    Select the trace approach to use. Defaults to deducing one
    based on your node's client-version and available RPCs.
    """

    request_headers: dict = {}
    """
    Optionally specify request headers to use whenever using this provider.
    """

    rpc_api: Optional[list[str]] = None
    """
    RPC APIs to enable. Defaults to all geth APIs.
    """

    model_config = SettingsConfigDict(extra="allow", env_prefix="APE_NODE_")

    @field_validator("call_trace_approach", mode="before")
    @classmethod
    def validate_trace_approach(cls, value):
        # This handles nicer config values.
        return None if value is None else TraceApproach.from_key(value)

    @field_validator("executable", mode="before")
    @classmethod
    def validate_executable(cls, value):
        if not value:
            return None

        elif isinstance(value, str):
            return value.split(" ")

        return value


class NodeSoftwareNotInstalledError(ConnectionError):
    def __init__(self):
        super().__init__(
            "No node found and 'ape-node' is unable to start one.\n"
            "Things you can do:\n"
            "\t1. Check your connection URL, if trying to connect remotely.\n"
            "\t2. Install node software (geth), if trying to run a local node.\n"
            "\t3. Use and configure a different provider plugin, such as 'ape-foundry'."
        )


# NOTE: Using EthereumNodeProvider because of it's geth-derived default behavior.
# TODO: In 0.9, change NAME to be `gethdev`, so for local networks it is more obvious.
class GethDev(EthereumNodeProvider, TestProviderAPI, SubprocessProvider):
    _process: Optional[GethDevProcess] = None
    name: str = "node"

    @property
    def process_name(self) -> str:
        if self._process:
            return self._process.process_name

        elif exec_cfg := self.config.executable:
            return get_node_name_from_executable(exec_cfg[0])

        return "geth"

    @property
    def chain_id(self) -> int:
        return self.settings.ethereum.local.get("chain_id", DEFAULT_TEST_CHAIN_ID)

    @property
    def block_time(self) -> Optional[int]:
        return self.settings.ethereum.local.get("block_time")

    @property
    def data_dir(self) -> Path:
        # Overridden from base class for placing debug logs in ape data folder.
        return self.settings.data_dir or self.config_manager.DATA_FOLDER / self.name

    @log_instead_of_fail(default="<node>")
    def __repr__(self) -> str:
        client_version = self.client_version
        client_version_str = f" ({client_version}) " if client_version else " "
        return f"<Node{client_version_str}chain_id={self.chain_id}>"

    @property
    def auto_mine(self) -> bool:
        if self.process is not None:
            # Geth --dev auto mines.
            return True

        try:
            return self.make_request("eth_mining", [])
        except NotImplementedError:
            # Assume true; unlikely to be off. Geth --dev automines.
            return True

    @auto_mine.setter
    def auto_mine(self, value):
        raise NotImplementedError("'auto_mine' setter not implemented.")

    @property
    def ipc_path(self) -> Optional[Path]:
        if rpc := self._configured_ipc_path:
            # "ipc_path" found in config/settings
            return Path(rpc)

        elif rpc := self._configured_uri:
            if f"{rpc}".endswith(".ipc"):
                # "uri" found in config/settings and is IPC.
                return Path(rpc)

        elif proc := self._process:
            # Connected.
            return Path(proc.ipc_path)

        # Default (used by geth-process).
        return self.data_dir / self.process_name / f"{self.process_name}.ipc"

    def connect(self):
        self._set_web3()
        if self.is_connected:
            self._complete_connect()

        elif self.allow_start:
            # Starting the process.
            self.start()
            atexit.register(self._disconnect_atexit)

    def start(self, timeout: int = 20):
        geth_dev = self._create_process()
        geth_dev.connect(timeout=timeout)
        if not self.web3.is_connected():
            geth_dev.disconnect()

            raise ConnectionError(f"Unable to connect to locally running {geth_dev.process_name}.")
        else:
            self.web3.middleware_onion.inject(ExtraDataToPOAMiddleware, layer=0)

        self._process = geth_dev

        # For subprocess-provider
        if self._process is not None and (process := self._process.proc):
            self.stderr_queue = JoinableQueue()
            self.stdout_queue = JoinableQueue()

            self.process = process

            # Start listening to output.
            spawn(self.produce_stdout_queue)
            spawn(self.produce_stderr_queue)
            spawn(self.consume_stdout_queue)
            spawn(self.consume_stderr_queue)

            self.network_manager.running_nodes.cache_provider(self)

    def _create_process(self) -> GethDevProcess:
        # NOTE: Using JSON mode to ensure types can be passed as CLI args.
        test_config = self.config_manager.get_config("test").model_dump(mode="json")

        # Allow configuring a custom executable besides your $PATH geth.
        if self.settings.executable is not None:
            test_config["executable"] = self.settings.executable

        test_config["ipc_path"] = self.ipc_path

        # Let the provider handle disconnecting the process.
        # This avoids multiple atexit handlers from being unnecessarily
        # registered that do some of the same thing.
        test_config["auto_disconnect"] = False

        # Include extra accounts to allocated funds to at genesis.
        extra_accounts = self.settings.ethereum.local.get("extra_funded_accounts", [])
        extra_accounts.extend(self.provider_settings.get("extra_funded_accounts", []))
        extra_accounts = list({a.lower() for a in extra_accounts})
        test_config["extra_funded_accounts"] = extra_accounts
        test_config["initial_balance"] = self.test_config.balance
        test_config["background"] = self.background
        uri = self.ws_uri or self.uri
        proc_data_dir = self.data_dir / f"{self.process_name}"
        return GethDevProcess.from_uri(
            uri,
            proc_data_dir,
            block_time=self.block_time,
            **test_config,
        )

    def disconnect(self):
        # Must disconnect process first.
        if self._process is not None:
            self._process.disconnect()
            self._process = None

            # Remove self from managed-processes list.
            self.network_manager.running_nodes.remove_provider(self)

        # Also unset the subprocess-provider reference.
        # NOTE: Type ignore is wrong; TODO: figure out why.
        self.process = None  # type: ignore[assignment]

        # Clear any snapshots.
        self.chain_manager._snapshots[self.chain_id] = []

        super().disconnect()

    def send_transaction(self, txn: "TransactionAPI") -> "ReceiptAPI":
        return self._send_transaction_with_retries(txn)

    def _send_transaction_with_retries(
        self, txn: "TransactionAPI", nonce_retries: int = 0, max_nonce_retries: int = 5
    ) -> "ReceiptAPI":
        try:
            return super().send_transaction(txn)
        except VirtualMachineError as err:
            if (
                txn.sender in self.account_manager.test_accounts
                and "exceeds block gas limit" in str(err)
            ):
                # Changed, possibly due to other transactions (x-dist?).
                # Retry using block gas limit.
                block_gas_limit = self.chain_manager.blocks.head.gas_limit
                if txn.gas_limit > block_gas_limit:
                    txn.gas_limit = block_gas_limit
                elif txn.gas_limit == block_gas_limit:
                    txn.gas_limit -= 1
                else:
                    # Raise whatever error it is. I am not sure how this is possible!
                    raise

                account = self.account_manager.test_accounts[txn.sender]
                signed_transaction = account.sign_transaction(txn)
                logger.debug("Gas-limit exceeds block gas limit. Retrying using block gas limit.")
                return super().send_transaction(signed_transaction)

            elif txn.sender in self.account_manager.test_accounts and re.match(
                r".*Nonce '\d*' is too low.*", str(err)
            ):
                retries = nonce_retries + 1
                if retries > max_nonce_retries:
                    raise  # This error.

                # Try again with a new nonce.
                account = self.account_manager.test_accounts[txn.sender]
                txn.nonce = account.nonce
                signed_transaction = account.sign_transaction(txn)
                logger.debug("Test transaction received bad nonce. Retrying using latest nonce.")
                return self._send_transaction_with_retries(
                    signed_transaction,
                    nonce_retries=retries,
                    max_nonce_retries=max_nonce_retries,
                )

            raise  # Whatever error it already is (Ape-ified from ape-ethereum.provider base).

    def snapshot(self) -> "SnapshotID":
        return self._get_latest_block().number or 0

    def restore(self, snapshot_id: "SnapshotID"):
        if isinstance(snapshot_id, int):
            block_number_int = snapshot_id
            block_number_hex_str = str(to_hex(snapshot_id))
        elif isinstance(snapshot_id, bytes):
            block_number_hex_str = add_0x_prefix(to_hex(snapshot_id))
            block_number_int = int(block_number_hex_str, 16)
        else:
            block_number_hex_str = to_hex(snapshot_id)
            block_number_int = int(snapshot_id, 16)

        current_block = self._get_latest_block().number
        if block_number_int == current_block:
            # Head is already at this block.
            return
        elif block_number_int > block_number_int:
            logger.error("Unable to set head to future block.")
            return

        self.make_request("debug_setHead", [block_number_hex_str])

    @raises_not_implemented
    def set_timestamp(self, new_timestamp: int):
        pass

    @raises_not_implemented
    def mine(self, num_blocks: int = 1):
        pass

    def build_command(self) -> list[str]:
        return self._process.command if self._process else []

    def get_test_account(self, index: int) -> "TestAccountAPI":
        if self._process is None:
            # Not managing the process. Use default approach.
            test_container = self.account_manager.test_accounts.containers["test"]
            return test_container.generate_account(index)

        # perf: we avoid having to generate account keys twice by utilizing
        #   the accounts generated for geth's genesis.json.
        account = self._process._dev_accounts[index]
        return self.account_manager.init_test_account(index, account.address, account.private_key)


# NOTE: The default behavior of EthereumNodeBehavior assumes geth.
class Node(EthereumNodeProvider):
    pass
