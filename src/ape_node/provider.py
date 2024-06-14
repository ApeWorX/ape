import atexit
import shutil
from pathlib import Path
from subprocess import DEVNULL, PIPE, Popen
from typing import Optional, Union

from eth_pydantic_types import HexBytes
from eth_typing import HexStr
from eth_utils import add_0x_prefix, to_hex, to_wei
from evmchains import get_random_rpc
from geth.accounts import ensure_account_exists  # type: ignore
from geth.chain import initialize_chain  # type: ignore
from geth.process import BaseGethProcess  # type: ignore
from geth.wrapper import construct_test_chain_kwargs  # type: ignore
from pydantic_settings import SettingsConfigDict
from requests.exceptions import ConnectionError
from web3.middleware import geth_poa_middleware
from yarl import URL

from ape.api import PluginConfig, SubprocessProvider, TestProviderAPI
from ape.logging import LogLevel, logger
from ape.types import SnapshotID
from ape.utils import (
    DEFAULT_NUMBER_OF_TEST_ACCOUNTS,
    DEFAULT_TEST_CHAIN_ID,
    DEFAULT_TEST_HD_PATH,
    DEFAULT_TEST_MNEMONIC,
    JoinableQueue,
    generate_dev_accounts,
    log_instead_of_fail,
    raises_not_implemented,
    spawn,
)
from ape_ethereum.provider import (
    DEFAULT_HOSTNAME,
    DEFAULT_PORT,
    DEFAULT_SETTINGS,
    EthereumNodeProvider,
)


class GethDevProcess(BaseGethProcess):
    """
    A developer-configured geth that only exists until disconnected.
    """

    def __init__(
        self,
        data_dir: Path,
        hostname: str = DEFAULT_HOSTNAME,
        port: int = DEFAULT_PORT,
        mnemonic: str = DEFAULT_TEST_MNEMONIC,
        number_of_accounts: int = DEFAULT_NUMBER_OF_TEST_ACCOUNTS,
        chain_id: int = DEFAULT_TEST_CHAIN_ID,
        initial_balance: Union[str, int] = to_wei(10000, "ether"),
        executable: Optional[str] = None,
        auto_disconnect: bool = True,
        extra_funded_accounts: Optional[list[str]] = None,
        hd_path: Optional[str] = DEFAULT_TEST_HD_PATH,
    ):
        executable = executable or "geth"
        if not shutil.which(executable):
            raise NodeSoftwareNotInstalledError()

        self.data_dir = data_dir
        self._hostname = hostname
        self._port = port
        self.data_dir.mkdir(exist_ok=True, parents=True)
        self.is_running = False
        self._auto_disconnect = auto_disconnect

        geth_kwargs = construct_test_chain_kwargs(
            data_dir=self.data_dir,
            geth_executable=executable,
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
        geth_kwargs["miner_etherbase"] = sealer
        accounts = generate_dev_accounts(
            mnemonic, number_of_accounts=number_of_accounts, hd_path=hd_path or DEFAULT_TEST_HD_PATH
        )
        addresses = [a.address for a in accounts]
        addresses.extend(extra_funded_accounts or [])
        bal_dict = {"balance": str(initial_balance)}
        alloc = {a: bal_dict for a in addresses}
        genesis_data: dict = {
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
                "shanghaiTime": 0,
                "clique": {"period": 0, "epoch": 30000},
            },
            "alloc": alloc,
        }

        initialize_chain(genesis_data, **geth_kwargs)
        self.proc: Optional[Popen] = None
        super().__init__(geth_kwargs)

    @classmethod
    def from_uri(cls, uri: str, data_folder: Path, **kwargs):
        parsed_uri = URL(uri)

        if parsed_uri.host not in ("localhost", "127.0.0.1"):
            raise ConnectionError(f"Unable to start Geth on non-local host {parsed_uri.host}.")

        port = parsed_uri.port if parsed_uri.port is not None else DEFAULT_PORT
        mnemonic = kwargs.get("mnemonic", DEFAULT_TEST_MNEMONIC)
        number_of_accounts = kwargs.get("number_of_accounts", DEFAULT_NUMBER_OF_TEST_ACCOUNTS)
        extra_accounts = [
            HexBytes(a).hex().lower() for a in kwargs.get("extra_funded_accounts", [])
        ]

        return cls(
            data_folder,
            hostname=parsed_uri.host,
            port=port,
            mnemonic=mnemonic,
            number_of_accounts=number_of_accounts,
            executable=kwargs.get("executable"),
            auto_disconnect=kwargs.get("auto_disconnect", True),
            extra_funded_accounts=extra_accounts,
            hd_path=kwargs.get("hd_path", DEFAULT_TEST_HD_PATH),
        )

    def connect(self, timeout: int = 60):
        home = str(Path.home())
        ipc_path = self.ipc_path.replace(home, "$HOME")
        logger.info(f"Starting geth (HTTP='{self._hostname}:{self._port}', IPC={ipc_path}).")
        self.start()
        self.wait_for_rpc(timeout=timeout)

        # Register atexit handler to make sure disconnect is called for normal object lifecycle.
        if self._auto_disconnect:
            atexit.register(self.disconnect)

    def start(self):
        if self.is_running:
            return

        self.is_running = True
        out_file = PIPE if logger.level <= LogLevel.DEBUG else DEVNULL
        self.proc = Popen(
            self.command,
            stdin=PIPE,
            stdout=out_file,
            stderr=out_file,
        )

    def disconnect(self):
        if self.is_running:
            logger.info("Stopping 'geth' process.")
            self.stop()

        self._clean()

    def _clean(self):
        if self.data_dir.is_dir():
            shutil.rmtree(self.data_dir)

    def wait(self, *args, **kwargs):
        if self.proc is None:
            return

        self.proc.wait(*args, **kwargs)


class EthereumNetworkConfig(PluginConfig):
    # Make sure you are running the right networks when you try for these
    mainnet: dict = {"uri": get_random_rpc("ethereum", "mainnet")}
    holesky: dict = {"uri": get_random_rpc("ethereum", "holesky")}
    sepolia: dict = {"uri": get_random_rpc("ethereum", "sepolia")}
    # Make sure to run via `geth --dev` (or similar)
    local: dict = {**DEFAULT_SETTINGS.copy(), "chain_id": DEFAULT_TEST_CHAIN_ID}

    model_config = SettingsConfigDict(extra="allow")


class EthereumNodeConfig(PluginConfig):
    ethereum: EthereumNetworkConfig = EthereumNetworkConfig()
    executable: Optional[str] = None
    ipc_path: Optional[Path] = None
    data_dir: Optional[Path] = None

    model_config = SettingsConfigDict(extra="allow")


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
class GethDev(EthereumNodeProvider, TestProviderAPI, SubprocessProvider):
    _process: Optional[GethDevProcess] = None
    name: str = "node"

    @property
    def process_name(self) -> str:
        return self.name

    @property
    def chain_id(self) -> int:
        return self.settings.ethereum.local.get("chain_id", DEFAULT_TEST_CHAIN_ID)

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
        return self.make_request("eth_mining", [])

    @auto_mine.setter
    def auto_mine(self, value):
        raise NotImplementedError("'auto_mine' setter not implemented.")

    def connect(self):
        self._set_web3()
        if self.is_connected:
            self._complete_connect()
        else:
            self.start()

    def start(self, timeout: int = 20):
        # NOTE: Using JSON mode to ensure types can be passed as CLI args.
        test_config = self.config_manager.get_config("test").model_dump(mode="json")

        # Allow configuring a custom executable besides your $PATH geth.
        if self.settings.executable is not None:
            test_config["executable"] = self.settings.executable

        test_config["ipc_path"] = self.ipc_path
        test_config["auto_disconnect"] = self._test_runner is None or test_config.get(
            "disconnect_providers_after", True
        )

        # Include extra accounts to allocated funds to at genesis.
        extra_accounts = self.settings.ethereum.local.get("extra_funded_accounts", [])
        extra_accounts.extend(self.provider_settings.get("extra_funded_accounts", []))
        extra_accounts = list({HexBytes(a).hex().lower() for a in extra_accounts})
        test_config["extra_funded_accounts"] = extra_accounts

        process = GethDevProcess.from_uri(self.uri, self.data_dir, **test_config)
        process.connect(timeout=timeout)
        if not self.web3.is_connected():
            process.disconnect()
            raise ConnectionError("Unable to connect to locally running geth.")
        else:
            self.web3.middleware_onion.inject(geth_poa_middleware, layer=0)

        self._process = process

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

    def disconnect(self):
        # Must disconnect process first.
        if self._process is not None:
            self._process.disconnect()
            self._process = None

        # Also unset the subprocess-provider reference.
        # NOTE: Type ignore is wrong; TODO: figure out why.
        self.process = None  # type: ignore[assignment]

        super().disconnect()

    def snapshot(self) -> SnapshotID:
        return self.get_block("latest").number or 0

    def restore(self, snapshot_id: SnapshotID):
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

        self.make_request("debug_setHead", [block_number_hex_str])

    @raises_not_implemented
    def set_timestamp(self, new_timestamp: int):
        pass

    @raises_not_implemented
    def mine(self, num_blocks: int = 1):
        pass

    def build_command(self) -> list[str]:
        return self._process.command if self._process else []


# NOTE: The default behavior of EthereumNodeBehavior assumes geth.
class Node(EthereumNodeProvider):
    pass
