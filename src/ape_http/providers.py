from typing import Iterator, Optional

from web3 import HTTPProvider, Web3
from web3.exceptions import ContractLogicError as Web3ContractLogicError
from web3.gas_strategies.rpc import rpc_gas_price_strategy
from web3.middleware import geth_poa_middleware
from web3.types import NodeInfo

from ape.api import ProviderAPI, ReceiptAPI, TransactionAPI
from ape.api.config import ConfigItem
from ape.exceptions import (
    ContractLogicError,
    OutOfGasError,
    ProviderError,
    TransactionError,
    VirtualMachineError,
)
from ape.utils import extract_nested_value, gas_estimation_error_message

DEFAULT_SETTINGS = {"uri": "http://localhost:8545", "chain_name": "devchain"}


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


class EthereumProvider(ProviderAPI):
    _web3: Web3 = None  # type: ignore

    @property
    def uri(self) -> str:
        return getattr(self.config, self.network.ecosystem.name)[self.network.name]["uri"]

    def connect(self):
        self._web3 = Web3(HTTPProvider(self.uri))
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

            message = gas_estimation_error_message(tx_error)
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
            # Unsupported API in user's geth.
            return None

    def get_nonce(self, address: str) -> int:
        """q
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
