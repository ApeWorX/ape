from eth_tester.backends import PyEVMBackend  # type: ignore
from eth_tester.exceptions import TransactionFailed  # type: ignore
from eth_utils.exceptions import ValidationError
from web3 import EthereumTesterProvider, Web3

from ape.api import ReceiptAPI, TestProviderAPI, TransactionAPI, Web3Provider
from ape.exceptions import ContractLogicError, OutOfGasError, TransactionError, VirtualMachineError
from ape.utils import gas_estimation_error_message


class LocalNetwork(TestProviderAPI, Web3Provider):
    def connect(self):
        pass

    def disconnect(self):
        pass

    def update_settings(self, new_settings: dict):
        pass

    def __post_init__(self):
        self._tester = PyEVMBackend.from_mnemonic(
            self.config["mnemonic"], num_accounts=self.config["number_of_accounts"]
        )
        self._web3 = Web3(EthereumTesterProvider(ethereum_tester=self._tester))

    def estimate_gas_cost(self, txn: TransactionAPI) -> int:
        try:
            return self._web3.eth.estimate_gas(txn.as_dict())  # type: ignore
        except ValidationError as err:
            message = gas_estimation_error_message(err)
            raise TransactionError(base_err=err, message=message) from err
        except TransactionFailed as err:
            raise _get_vm_err(err) from err

    @property
    def gas_price(self) -> int:
        return self.base_fee  # no miner tip

    @property
    def priority_fee(self) -> int:
        """Returns 0 because test chains do not care about priority fees."""
        return 0

    def send_call(self, txn: TransactionAPI) -> bytes:
        data = txn.as_dict()
        if "gas" not in data or data["gas"] == 0:
            data["gas"] = int(1e12)
        return self._web3.eth.call(data)

    def send_transaction(self, txn: TransactionAPI) -> ReceiptAPI:
        try:
            txn_hash = self._web3.eth.send_raw_transaction(txn.encode())
        except ValidationError as err:
            raise VirtualMachineError(base_err=err) from err
        except TransactionFailed as err:
            raise _get_vm_err(err) from err

        receipt = self.get_transaction(txn_hash.hex())
        if txn.gas_limit is not None and receipt.ran_out_of_gas:
            raise OutOfGasError()

        return receipt

    def snapshot(self) -> str:
        return self._tester.take_snapshot()

    def revert(self, snapshot_id: str):
        if snapshot_id:
            return self._tester.revert_to_snapshot(snapshot_id)


def _get_vm_err(web3_err: TransactionFailed) -> ContractLogicError:
    err_message = str(web3_err).split("execution reverted: ")[-1] or None
    return ContractLogicError(revert_message=err_message)
