from typing import Any, Iterator

from eth_keys import KeyAPI  # type: ignore
from eth_tester.backends import PyEVMBackend  # type: ignore
from eth_tester.backends.pyevm.main import (  # type: ignore
    generate_genesis_state_for_keys,
    get_default_genesis_params,
)
from eth_tester.exceptions import TransactionFailed  # type: ignore
from eth_utils import to_wei
from eth_utils.exceptions import ValidationError
from eth_utils.toolz import assoc
from hexbytes import HexBytes
from web3 import EthereumTesterProvider, Web3

from ape.api import ProviderAPI, ReceiptAPI, TransactionAPI, TransactionStatusEnum
from ape.exceptions import ContractLogicError, OutOfGasError, VirtualMachineError
from ape.utils import generate_dev_accounts


def _setup_tester_chain(
    genesis_params=None, genesis_state=None, num_accounts=None, vm_configuration=None
):

    from eth.chains.base import MiningChain
    from eth.consensus import ConsensusApplier, NoProofConsensus
    from eth.db import get_db_backend

    if vm_configuration is None:
        from eth.vm.forks import BerlinVM

        no_proof_vms = ((0, BerlinVM.configure(consensus_class=NoProofConsensus)),)
    else:
        consensus_applier = ConsensusApplier(NoProofConsensus)
        no_proof_vms = consensus_applier.amend_vm_configuration(vm_configuration)

    class MainnetTesterNoProofChain(MiningChain):
        vm_configuration = no_proof_vms

        def create_header_from_parent(self, parent_header, **header_params):
            # Keep the gas limit constant
            return super().create_header_from_parent(
                parent_header, **assoc(header_params, "gas_limit", parent_header.gas_limit)
            )

    if genesis_params is None:
        genesis_params = get_default_genesis_params()

    if genesis_state:
        num_accounts = len(genesis_state)

    account_keys = _get_test_keys(number_of_accounts=num_accounts)
    if genesis_state is None:
        genesis_state = generate_genesis_state_for_keys(account_keys)

    base_db = get_db_backend()

    chain = MainnetTesterNoProofChain.from_genesis(base_db, genesis_params, genesis_state)
    return account_keys, chain


def _get_test_keys(number_of_accounts: int):
    keys = KeyAPI()
    accounts = generate_dev_accounts(number_of_accounts=number_of_accounts)
    return [keys.PrivateKey(HexBytes(a.private_key)) for a in accounts]


class TestEVMBackend(PyEVMBackend):
    """
    An EVM backend populated with accounts using the test mnemonic.
    """

    def __init__(self, number_of_accounts: int = 10, initial_ether: int = 10000):
        account_keys = _get_test_keys(number_of_accounts=number_of_accounts)
        genesis_state = generate_genesis_state_for_keys(
            account_keys=account_keys, overrides={"balance": to_wei(initial_ether, "ether")}
        )
        super().__init__(genesis_state=genesis_state)

    def reset_to_genesis(
        self, genesis_params=None, genesis_state=None, num_accounts=None, vm_configuration=None
    ):
        """Override to use our version of `setup_tester_chain` that uses
        ape-configured accounts rather than the one `eth-tester` uses.
        """
        self.account_keys, self.chain = _setup_tester_chain(
            genesis_params,
            genesis_state,
            num_accounts,
            vm_configuration,
        )


class LocalNetwork(ProviderAPI):
    _web3: Web3 = None  # type: ignore

    def connect(self):
        pass

    def disconnect(self):
        pass

    def update_settings(self, new_settings: dict):
        pass

    def __post_init__(self):
        self._backend = TestEVMBackend()
        self._web3 = Web3(EthereumTesterProvider(ethereum_tester=self._backend))

    def estimate_gas_cost(self, txn: TransactionAPI) -> int:
        try:
            return self._web3.eth.estimate_gas(txn.as_dict())  # type: ignore
        except TransactionFailed as err:
            err_message = str(err).split("execution reverted: ")[-1]
            raise ContractLogicError(err_message) from err

    @property
    def chain_id(self) -> int:
        return self._web3.eth.chain_id

    @property
    def gas_price(self):
        # NOTE: Test chain doesn't care about gas prices
        return 0

    def get_nonce(self, address: str) -> int:
        return self._web3.eth.get_transaction_count(address)  # type: ignore

    def get_balance(self, address: str) -> int:
        return self._web3.eth.get_balance(address)  # type: ignore

    def get_code(self, address: str) -> bytes:
        return self._web3.eth.get_code(address)  # type: ignore

    def send_call(self, txn: TransactionAPI) -> bytes:
        data = txn.as_dict()
        if "gas" not in data or data["gas"] == 0:
            data["gas"] = int(1e12)
        return self._web3.eth.call(data)

    def get_transaction(self, txn_hash: str) -> ReceiptAPI:
        # TODO: Work on API that let's you work with ReceiptAPI and re-send transactions
        receipt = self._web3.eth.wait_for_transaction_receipt(txn_hash)  # type: ignore
        txn = self._web3.eth.get_transaction(txn_hash)  # type: ignore
        return self.network.ecosystem.receipt_class.decode({**txn, **receipt})

    def send_transaction(self, txn: TransactionAPI) -> ReceiptAPI:
        try:
            txn_hash = self._web3.eth.send_raw_transaction(txn.encode())
        except ValidationError as err:
            raise VirtualMachineError(err) from err
        except TransactionFailed as err:
            err_message = str(err).split("execution reverted: ")[-1]
            raise ContractLogicError(err_message) from err

        receipt = self.get_transaction(txn_hash.hex())

        if receipt.status == TransactionStatusEnum.FAILING and receipt.gas_used == txn.gas_limit:
            raise OutOfGasError()

        return receipt

    def get_events(self, **filter_params) -> Iterator[dict]:
        return iter(self._web3.eth.get_logs(filter_params))  # type: ignore

    def snapshot(self) -> Any:
        return self._backend.take_snapshot()

    def revert(self, snapshot_id: Any):
        if snapshot_id:
            return self._backend.revert_to_snapshot(snapshot_id)
