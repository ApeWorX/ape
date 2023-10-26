import operator
import re
from ast import literal_eval
from typing import Dict, Optional, cast

from eth.exceptions import HeaderNotFound
from eth_tester.backends import PyEVMBackend  # type: ignore
from eth_tester.exceptions import FilterNotFound, TransactionFailed  # type: ignore
from eth_utils import decode_hex, encode_hex, is_0x_prefixed, is_null, keccak
from eth_utils.curried import apply_formatter_if
from eth_utils.exceptions import ValidationError
from eth_utils.toolz import compose, excepts
from ethpm_types import HexBytes
from web3 import EthereumTesterProvider, Web3
from web3.exceptions import ContractPanicError
from web3.providers.eth_tester.defaults import (
    call_eth_tester,
    client_version,
    create_log_filter,
    create_new_account,
    get_logs,
    get_transaction_by_block_hash_and_index,
    get_transaction_by_block_number_and_index,
    not_implemented,
    null_if_block_not_found,
    null_if_filter_not_found,
    null_if_transaction_not_found,
    personal_send_transaction,
    static_return,
    without_eth_tester,
)
from web3.types import TxParams

from ape.api import PluginConfig, ReceiptAPI, TestProviderAPI, TransactionAPI, Web3Provider
from ape.exceptions import (
    ContractLogicError,
    ProviderError,
    ProviderNotConnectedError,
    TransactionError,
    UnknownSnapshotError,
    VirtualMachineError,
)
from ape.types import SnapshotID
from ape.utils import DEFAULT_TEST_CHAIN_ID, gas_estimation_error_message


class EthTesterProviderConfig(PluginConfig):
    chain_id: int = DEFAULT_TEST_CHAIN_ID


class LocalProvider(TestProviderAPI, Web3Provider):
    _evm_backend: Optional[PyEVMBackend] = None
    _CANNOT_AFFORD_GAS_PATTERN = re.compile(
        r"Sender b'[\\*|\w]*' cannot afford txn gas (\d+) with account balance (\d+)"
    )
    _INVALID_NONCE_PATTERN = re.compile(r"Invalid transaction nonce: Expected (\d+), but got (\d+)")

    @property
    def evm_backend(self) -> PyEVMBackend:
        if self._evm_backend is None:
            raise ProviderNotConnectedError()

        return self._evm_backend

    def connect(self):
        chain_id = self.settings.chain_id
        if self._web3 is not None:
            connected_chain_id = self._make_request("eth_chainId")
            if connected_chain_id == chain_id:
                # Is already connected and settings have not changed.
                return

        self._evm_backend = PyEVMBackend.from_mnemonic(
            mnemonic=self.config.mnemonic,
            num_accounts=self.config.number_of_accounts,
        )
        endpoints = get_endpoints()
        endpoints["eth"]["chainId"] = static_return(chain_id)
        tester = EthereumTesterProvider(ethereum_tester=self._evm_backend, api_endpoints=endpoints)
        self._web3 = Web3(tester)

    def disconnect(self):
        self.cached_chain_id = None
        self._web3 = None
        self._evm_backend = None
        self.provider_settings = {}

    def update_settings(self, new_settings: Dict):
        self.cached_chain_id = None
        self.provider_settings = {**self.provider_settings, **new_settings}
        self.disconnect()
        self.connect()

    def estimate_gas_cost(self, txn: TransactionAPI, **kwargs) -> int:
        if isinstance(self.network.gas_limit, int):
            return self.network.gas_limit

        elif self.network.gas_limit == "max":
            block = self.web3.eth.get_block("latest")
            return block["gasLimit"]

        block_id = kwargs.pop("block_identifier", kwargs.pop("block_id", None))
        estimate_gas = self.web3.eth.estimate_gas
        txn_dict = txn.dict()
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
                value = estimate_gas(txn.dict(), block_identifier=block_id)  # type: ignore
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
        return EthTesterProviderConfig.parse_obj(
            {**self.config.provider.dict(), **self.provider_settings}
        )

    @property
    def chain_id(self) -> int:
        if self.cached_chain_id:
            return self.cached_chain_id

        try:
            result = self._make_request("eth_chainId")
        except ProviderNotConnectedError:
            result = self.settings.chain_id

        self.cached_chain_id = result
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

    def send_call(self, txn: TransactionAPI, **kwargs) -> bytes:
        data = txn.dict(exclude_none=True)
        block_id = kwargs.pop("block_identifier", kwargs.pop("block_id", None))
        state = kwargs.pop("state_override", None)
        call_kwargs = {"block_identifier": block_id, "state_override": state}

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
        return result

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
            txn_dict = txn.dict()
            txn_dict["nonce"] += 1
            txn_params = cast(TxParams, txn_dict)

            # Replay txn to get revert reason
            try:
                self.web3.eth.call(txn_params)
            except (ValidationError, TransactionFailed) as err:
                vm_err = self.get_virtual_machine_error(err, txn=receipt)
                raise vm_err from err

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


def get_endpoints():
    # HACK: Until https://github.com/ethereum/web3.py/issues/3136 resolved.
    return {
        "web3": {
            "clientVersion": client_version,
            "sha3": compose(
                encode_hex,
                keccak,
                decode_hex,
                without_eth_tester(operator.itemgetter(0)),
            ),
        },
        "net": {
            "version": static_return("1"),
            "listening": static_return(False),
            "peerCount": static_return(0),
        },
        "eth": {
            "protocolVersion": static_return(63),
            "syncing": static_return(False),
            "coinbase": compose(
                operator.itemgetter(0),
                call_eth_tester("get_accounts"),
            ),
            "mining": static_return(False),
            "hashrate": static_return(0),
            "chainId": static_return(131277322940537),  # from fixture generation file
            "feeHistory": not_implemented,
            "maxPriorityFeePerGas": static_return(10**9),
            "gasPrice": static_return(10**9),  # must be >= base fee post-London
            "accounts": call_eth_tester("get_accounts"),
            "blockNumber": compose(
                operator.itemgetter("number"),
                call_eth_tester("get_block_by_number", fn_kwargs={"block_number": "latest"}),
            ),
            "getBalance": call_eth_tester("get_balance"),
            "getStorageAt": call_eth_tester("get_storage_at"),
            "getProof": not_implemented,
            "getTransactionCount": call_eth_tester("get_nonce"),
            "getBlockTransactionCountByHash": null_if_block_not_found(
                compose(
                    len,
                    operator.itemgetter("transactions"),
                    call_eth_tester("get_block_by_hash"),
                )
            ),
            "getBlockTransactionCountByNumber": null_if_block_not_found(
                compose(
                    len,
                    operator.itemgetter("transactions"),
                    call_eth_tester("get_block_by_number"),
                )
            ),
            "getUncleCountByBlockHash": null_if_block_not_found(
                compose(
                    len,
                    operator.itemgetter("uncles"),
                    call_eth_tester("get_block_by_hash"),
                )
            ),
            "getUncleCountByBlockNumber": null_if_block_not_found(
                compose(
                    len,
                    operator.itemgetter("uncles"),
                    call_eth_tester("get_block_by_number"),
                )
            ),
            "getCode": call_eth_tester("get_code"),
            "sign": not_implemented,
            "signTransaction": not_implemented,
            "sendTransaction": call_eth_tester("send_transaction"),
            "sendRawTransaction": call_eth_tester("send_raw_transaction"),
            "call": call_eth_tester("call"),  # TODO: untested
            "estimateGas": call_eth_tester("estimate_gas"),  # TODO: untested
            "getBlockByHash": null_if_block_not_found(call_eth_tester("get_block_by_hash")),
            "getBlockByNumber": null_if_block_not_found(call_eth_tester("get_block_by_number")),
            "getTransactionByHash": null_if_transaction_not_found(
                call_eth_tester("get_transaction_by_hash")
            ),
            "getTransactionByBlockHashAndIndex": get_transaction_by_block_hash_and_index,
            "getTransactionByBlockNumberAndIndex": get_transaction_by_block_number_and_index,  # noqa: E501
            "getTransactionReceipt": null_if_transaction_not_found(
                compose(
                    apply_formatter_if(
                        compose(is_null, operator.itemgetter("block_number")),
                        static_return(None),
                    ),
                    call_eth_tester("get_transaction_receipt"),
                )
            ),
            "getUncleByBlockHashAndIndex": not_implemented,
            "getUncleByBlockNumberAndIndex": not_implemented,
            "getCompilers": not_implemented,
            "compileLLL": not_implemented,
            "compileSolidity": not_implemented,
            "compileSerpent": not_implemented,
            "newFilter": create_log_filter,
            "newBlockFilter": call_eth_tester("create_block_filter"),
            "newPendingTransactionFilter": call_eth_tester("create_pending_transaction_filter"),
            "uninstallFilter": excepts(
                FilterNotFound,
                compose(
                    is_null,
                    call_eth_tester("delete_filter"),
                ),
                static_return(False),
            ),
            "getFilterChanges": null_if_filter_not_found(
                call_eth_tester("get_only_filter_changes")
            ),
            "getFilterLogs": null_if_filter_not_found(call_eth_tester("get_all_filter_logs")),
            "getLogs": get_logs,
            "getWork": not_implemented,
            "submitWork": not_implemented,
            "submitHashrate": not_implemented,
        },
        "db": {
            "putString": not_implemented,
            "getString": not_implemented,
            "putHex": not_implemented,
            "getHex": not_implemented,
        },
        "admin": {
            "add_peer": not_implemented,
            "datadir": not_implemented,
            "node_info": not_implemented,
            "peers": not_implemented,
            "start_http": not_implemented,
            "start_ws": not_implemented,
            "stop_http": not_implemented,
            "stop_ws": not_implemented,
        },
        "debug": {
            "backtraceAt": not_implemented,
            "blockProfile": not_implemented,
            "cpuProfile": not_implemented,
            "dumpBlock": not_implemented,
            "gtStats": not_implemented,
            "getBlockRLP": not_implemented,
            "goTrace": not_implemented,
            "memStats": not_implemented,
            "seedHashSign": not_implemented,
            "setBlockProfileRate": not_implemented,
            "setHead": not_implemented,
            "stacks": not_implemented,
            "startCPUProfile": not_implemented,
            "startGoTrace": not_implemented,
            "stopCPUProfile": not_implemented,
            "stopGoTrace": not_implemented,
            "traceBlock": not_implemented,
            "traceBlockByNumber": not_implemented,
            "traceBlockByHash": not_implemented,
            "traceBlockFromFile": not_implemented,
            "traceTransaction": not_implemented,
            "verbosity": not_implemented,
            "vmodule": not_implemented,
            "writeBlockProfile": not_implemented,
            "writeMemProfile": not_implemented,
        },
        "miner": {
            "make_dag": not_implemented,
            "set_extra": not_implemented,
            "set_gas_price": not_implemented,
            "start": not_implemented,
            "stop": not_implemented,
            "start_auto_dag": not_implemented,
            "stop_auto_dag": not_implemented,
        },
        "personal": {
            "ec_recover": not_implemented,
            "import_raw_key": call_eth_tester("add_account"),
            "list_accounts": call_eth_tester("get_accounts"),
            "list_wallets": not_implemented,
            "lock_account": excepts(
                ValidationError,
                compose(static_return(True), call_eth_tester("lock_account")),
                static_return(False),
            ),
            "new_account": create_new_account,
            "unlock_account": excepts(
                ValidationError,
                compose(static_return(True), call_eth_tester("unlock_account")),
                static_return(False),
            ),
            "send_transaction": personal_send_transaction,
            "sign": not_implemented,
            # deprecated
            "ecRecover": not_implemented,
            "importRawKey": call_eth_tester("add_account"),
            "listAccounts": call_eth_tester("get_accounts"),
            "lockAccount": excepts(
                ValidationError,
                compose(static_return(True), call_eth_tester("lock_account")),
                static_return(False),
            ),
            "newAccount": create_new_account,
            "unlockAccount": excepts(
                ValidationError,
                compose(static_return(True), call_eth_tester("unlock_account")),
                static_return(False),
            ),
            "sendTransaction": personal_send_transaction,
        },
        "testing": {
            "timeTravel": call_eth_tester("time_travel"),
        },
        "txpool": {
            "content": not_implemented,
            "inspect": not_implemented,
            "status": not_implemented,
        },
        "evm": {
            "mine": call_eth_tester("mine_blocks"),
            "revert": call_eth_tester("revert_to_snapshot"),
            "snapshot": call_eth_tester("take_snapshot"),
        },
    }
