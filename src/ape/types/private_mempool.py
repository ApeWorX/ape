"""
Much of the models here are heavily inspired from the rust Alloy crate ``alloy-rpc-types-mev``.
https://github.com/alloy-rs/alloy
"""

from collections.abc import Iterator
from enum import Enum
from typing import Optional, Union

from eth_pydantic_types.hex import HexBytes, HexBytes32, HexInt
from ethpm_types.abi import EventABI
from pydantic import ConfigDict, Field

from ape.exceptions import ProviderNotConnectedError
from ape.types import AddressType
from ape.utils.basemodel import BaseModel, ManagerAccessMixin


class ProtocolVersion(str, Enum):
    """
    The version of the MEV-share API to use.
    """

    BETA1 = "beta-1"
    """
    The beta-1 version of the API.
    """

    V0_1 = "v0.1"
    """
    The 0.1 version of the API.
    """


class Refund(BaseModel):
    """
    Specifies the minimum percent of a given bundle's earnings to redistribute for it to be included
    in a builder's block.
    """

    body_idx: HexInt
    """
    The index of the transaction in the bundle.
    """

    percent: HexInt
    """
    The minimum percent of the bundle's earnings to redistribute.
    """


class PrivacyHint(str, Enum):
    """
    Hints on what data should be shared about the bundle and its transactions.
    """

    CALLDATA = "calldata"
    """
    The calldata of the bundle's transactions should be shared.
    """

    CONTRACT_ADDRESS = "contract_address"
    """
    The address of the bundle's transactions should be shared.
    """

    LOGS = "logs"
    """
    The logs of the bundle's transactions should be shared.
    """

    FUNCTION_SELECTOR = "function_selector"
    """
    The function selector of the bundle's transactions should be shared.
    """

    HASH = "hash"
    """
    The hash of the bundle's transactions should be shared.
    """

    TX_HASH = "tx_hash"
    """
    The hash of the bundle should be shared.
    """


class Privacy(BaseModel):
    """
    Preferences on what data should be shared about the bundle and its transactions
    """

    hints: Optional[list[PrivacyHint]] = None
    """
    Hints on what data should be shared about the bundle and its transactions.
    """

    builders: Optional[list[str]] = None
    """
    Names of the builders that should be allowed to see the bundle/transaction.
    """


class Inclusion(BaseModel):
    """
    Data used by block builders to check if the bundle should be considered for inclusion.
    """

    block: HexInt
    """
    The first block the bundle is valid for.
    """

    max_block: Union[HexInt, None] = Field(None, alias="maxBlock")
    """
    The last block the bundle is valid for.
    """


class BundleHashItem(BaseModel):
    """
    The hash of either a transaction or bundle we are trying to backrun.
    """

    hash: HexBytes32
    """
    Tx hash.
    """


class BundleTxItem(BaseModel):
    """
    A new signed transaction.
    """

    model_config = ConfigDict(populate_by_name=True)

    tx: HexBytes
    """
    Bytes of the signed transaction.
    """

    can_revert: bool = Field(alias="canRevert")
    """
    If true, the transaction can revert without the bundle being considered invalid.
    """


class BundleNestedItem(BaseModel):
    """
    A nested bundle request.
    """

    bundle: "Bundle"
    """
    A bundle request of type Bundle
    """


class RefundConfig(BaseModel):
    """
    Specifies what addresses should receive what percent of the overall refund for this bundle,
    if it is enveloped by another bundle (e.g. a searcher backrun).
    """

    address: AddressType
    """
    The address to refund.
    """

    percent: int
    """
    The minimum percent of the bundle's earnings to redistribute.
    """


class Validity(BaseModel):
    """
    Requirements for the bundle to be included in the block.
    """

    refund: Union[list[Refund], None] = None
    """
    Specifies the minimum percent of a given bundle's earnings to redistribute
    for it to be included in a builder's block.
    """

    refund_config: Optional[list[RefundConfig]] = Field(None, alias="refundConfig")
    """
    Specifies what addresses should receive what percent of the overall refund for this bundle,
    if it is enveloped by another bundle (e.g. a searcher backrun).
    """


class Bundle(BaseModel):
    """
    A bundle of transactions to send to the matchmaker.
    """

    version: ProtocolVersion
    """
    The version of the MEV-share API to use.
    """

    inclusion: Inclusion
    """
    Data used by block builders to check if the bundle should be considered for inclusion.
    """

    body: list[Union[BundleHashItem, BundleTxItem, BundleNestedItem]]
    """
    The transactions to include in the bundle.
    """

    validity: Optional[Validity] = None
    """
    Requirements for the bundle to be included in the block.
    """

    privacy: Optional[Privacy] = None
    """
    Preferences on what data should be shared about the bundle and its transactions
    """

    @classmethod
    def build_for_block(
        cls,
        block: HexInt,
        max_block: Optional[HexInt] = None,
        version: Optional[ProtocolVersion] = None,
        body: Optional[list[Union[BundleHashItem, BundleTxItem, BundleNestedItem]]] = None,
        validity: Optional[Validity] = None,
        privacy: Optional[Privacy] = None,
    ) -> "Bundle":
        return cls(
            version=version or ProtocolVersion.V0_1,
            inclusion=Inclusion(block=block, max_block=max_block),
            body=body or [],
            validity=validity,
            privacy=privacy,
        )

    def add_tx(self, tx: HexBytes, can_revert: bool) -> "Bundle":
        self.body.append(BundleTxItem(tx=tx, can_revert=can_revert))
        return self

    def add_hash(self, hash: HexBytes32) -> "Bundle":
        self.body.append(BundleHashItem(hash=hash))
        return self

    def add_bundle(self, bundle: "Bundle"):
        self.body.append(BundleNestedItem(bundle=bundle))


class SimBundleLogs(BaseModel):
    """
    Logs returned by `mev_simBundle`.
    """

    tx_logs: Optional[list[dict]] = Field(None, alias="txLogs")
    """
    Logs for transactions in bundle.
    """

    bundle_logs: Optional[list["SimBundleLogs"]] = Field(None, alias="bundleLogs")
    """
    Logs for bundles in bundle.
    """


class SimulationReport(BaseModel):
    """
    Response from the matchmaker after sending a simulation request.
    """

    success: bool
    """
    Whether the simulation was successful.
    """

    error: Optional[str] = None
    """
    Error message if the simulation failed.
    """

    state_block: Optional[HexInt] = Field(None, alias="stateBlock")
    """
    The block number of the simulated block.
    """

    mev_gas_price: HexInt = Field(alias="mevGasPrice")
    """
    The profit of the simulated block.
    """

    profit: HexInt
    """
    The profit of the simulated block.
    """

    refundable_value: Optional[HexInt] = Field(None, alias="refundableValue")
    """
    The refundable value of the simulated block.
    """

    gas_used: Optional[HexInt] = Field(None, alias="gasUsed")
    """
    The gas used by the simulated block.
    """

    logs: Optional[list[SimBundleLogs]] = None
    """
    Logs returned by `mev_simBundle`.
    """

    exec_error: Optional[str] = Field(None, alias="execError")
    """
    Error message if the bundle execution failed.
    """

    revert: Optional[HexBytes] = None
    """
    Contains the return data if the transaction reverted
    """

    def decode_logs(self, *events: EventABI):
        try:
            ecosystem = ManagerAccessMixin.provider.network.ecosystem
        except ProviderNotConnectedError:
            # Assume Ethereum (since we are in ape-ethereum after all).
            ecosystem = ManagerAccessMixin.network_manager.ethereum

        return ecosystem.decode_logs(list(self.transaction_logs), *events)

    @property
    def transaction_logs(self, *events: EventABI) -> Iterator[dict]:
        yield from _get_transaction_logs_from_sim_logs(self.logs or [])


def _get_transaction_logs_from_sim_logs(logs: list[SimBundleLogs]) -> Iterator[dict]:
    for bundle_log in logs:
        yield from (bundle_log.tx_logs or [])
        yield from _get_transaction_logs_from_sim_logs(bundle_log.bundle_logs or [])
