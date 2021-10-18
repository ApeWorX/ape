from typing import Iterator

from web3 import HTTPProvider, Web3
from web3.gas_strategies.rpc import rpc_gas_price_strategy
from web3.middleware import geth_poa_middleware

from ape.api import ProviderAPI, ReceiptAPI, TransactionAPI
from ape.api.config import ConfigItem
from ape.exceptions import ProviderError, TransactionError, VirtualMachineError
from ape.utils import get_tx_error_from_web3_value_error

DEFAULT_SETTINGS = {"uri": "http://localhost:8545"}


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

        if self.network.name not in ("mainnet", "ropsten"):
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
            return self._web3.eth.estimate_gas(txn.as_dict())  # type: ignore
        except ValueError as err:
            tx_error = get_tx_error_from_web3_value_error(err)

            # If this is the cause of a would-be revert,
            # raise the VirtualMachineError so that we can confirm tx-reverts.
            if isinstance(tx_error, VirtualMachineError):
                raise tx_error from err

            message = (
                f"Gas estimation failed: '{tx_error}'. This transaction will likely revert. "
                "If you wish to broadcast, you must set the gas limit manually."
            )
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
            raise get_tx_error_from_web3_value_error(err) from err

        return self.get_transaction(txn_hash.hex())

    def get_events(self, **filter_params) -> Iterator[dict]:
        """
        Returns an array of all logs matching a given set of filter parameters.
        """
        return iter(self._web3.eth.get_logs(filter_params))  # type: ignore
