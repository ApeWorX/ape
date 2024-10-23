from abc import abstractmethod
from collections.abc import Iterator, Sequence
from functools import cache, cached_property
from typing import Any, Optional, Union

from ethpm_types.abi import EventABI, MethodABI
from pydantic import NonNegativeInt, PositiveInt, model_validator

from ape.api.transactions import ReceiptAPI, TransactionAPI
from ape.logging import logger
from ape.types.address import AddressType
from ape.utils.basemodel import BaseInterface, BaseInterfaceModel, BaseModel

QueryType = Union[
    "BlockQuery",
    "BlockTransactionQuery",
    "AccountTransactionQuery",
    "ContractCreationQuery",
    "ContractEventQuery",
    "ContractMethodQuery",
]


@cache
def _basic_columns(Model: type[BaseInterfaceModel]) -> set[str]:
    columns = set(Model.model_fields)

    # TODO: Remove once `ReceiptAPI` fields cleaned up for better processing
    if Model == ReceiptAPI:
        columns.remove("transaction")
        columns |= _basic_columns(TransactionAPI)

    return columns


@cache
def _all_columns(Model: type[BaseInterfaceModel]) -> set[str]:
    columns = _basic_columns(Model)
    # NOTE: Iterate down the series of subclasses of `Model` (e.g. Block and BlockAPI)
    #       and get all of the public property methods of each class (which are valid columns)
    columns |= {
        field_name
        for cls in Model.__mro__
        if issubclass(cls, BaseInterfaceModel) and cls is not BaseInterfaceModel
        for field_name, field in vars(cls).items()
        if not field_name.startswith("_") and isinstance(field, (property, cached_property))
    }

    # TODO: Remove once `ReceiptAPI` fields cleaned up for better processing
    if Model == ReceiptAPI:
        columns |= _all_columns(TransactionAPI)

    return columns


def validate_and_expand_columns(
    columns: Sequence[str], Model: type[BaseInterfaceModel]
) -> list[str]:
    if len(columns) == 1 and columns[0] == "*":
        # NOTE: By default, only pull explicit fields
        #       (because they are cheap to pull, but properties might not be)
        return sorted(_basic_columns(Model))

    else:
        # NOTE: Validate if selected columns in the total set of fields + properties
        all_columns = _all_columns(Model)
        deduped_columns = set(columns)
        if len(deduped_columns) != len(columns):
            logger.warning(f"Duplicate fields in {columns}")

        # NOTE: Some unrecognized fields, but can still provide the rest of the data
        if len(deduped_columns - all_columns) > 0:
            err_msg = _unrecognized_columns(deduped_columns, all_columns)
            logger.warning(err_msg)

        # NOTE: Only select recognized fields and return them (in sorted order)
        selected_fields = all_columns.intersection(deduped_columns)
        if len(selected_fields) > 0:
            return sorted(selected_fields)

    # NOTE: No recognized fields available to query, so raise ValueError
    err_msg = _unrecognized_columns(deduped_columns, all_columns)
    raise ValueError(err_msg)


def _unrecognized_columns(selected_columns: set[str], all_columns: set[str]) -> str:
    unrecognized = "', '".join(sorted(selected_columns - all_columns))
    all_cols = ", ".join(sorted(all_columns))
    return f"Unrecognized field(s) '{unrecognized}', must be one of '{all_cols}'."


def extract_fields(item: BaseInterfaceModel, columns: Sequence[str]) -> list[Any]:
    return [getattr(item, col, None) for col in columns]


class _BaseQuery(BaseModel):
    columns: Sequence[str]

    # TODO: Support "*" from getting the EcosystemAPI fields


class _BaseBlockQuery(_BaseQuery):
    start_block: NonNegativeInt = 0
    stop_block: NonNegativeInt
    step: PositiveInt = 1

    @model_validator(mode="before")
    @classmethod
    def check_start_block_before_stop_block(cls, values):
        start_block = values.get("start_block")
        stop_block = values.get("stop_block")
        if (
            isinstance(start_block, int)
            and isinstance(stop_block, int)
            and stop_block < start_block
        ):
            raise ValueError(
                f"stop_block: '{values['stop_block']}' cannot be less than "
                f"start_block: '{values['start_block']}'."
            )

        return values


class BlockQuery(_BaseBlockQuery):
    """
    A ``QueryType`` that collects properties of ``BlockAPI`` over a range of
    blocks between ``start_block`` and ``stop_block``.
    """


class BlockTransactionQuery(_BaseQuery):
    """
    A ``QueryType`` that collects properties of ``TransactionAPI`` over a range of
    transactions collected inside the ``BlockAPI` object represented by ``block_id``.
    """

    block_id: Any


class AccountTransactionQuery(_BaseQuery):
    """
    A ``QueryType`` that collects properties of ``TransactionAPI`` over a range
    of transactions made by ``account`` between ``start_nonce`` and ``stop_nonce``.
    """

    account: AddressType
    start_nonce: NonNegativeInt = 0
    stop_nonce: NonNegativeInt

    @model_validator(mode="before")
    @classmethod
    def check_start_nonce_before_stop_nonce(cls, values: dict) -> dict:
        if values["stop_nonce"] < values["start_nonce"]:
            raise ValueError(
                f"stop_nonce: '{values['stop_nonce']}' cannot be less than "
                f"start_nonce: '{values['start_nonce']}'."
            )

        return values


class ContractCreationQuery(_BaseQuery):
    """
    A ``QueryType`` that obtains information about contract deployment.
    Returns ``ContractCreation(txn_hash, block, deployer, factory)``.
    """

    contract: AddressType


class ContractCreation(BaseModel, BaseInterface):
    """
    Contract-creation metadata, such as the transaction
    and deployer. Useful for contract-verification,
    ``block_identifier=`` usage, and other use-cases.

    To get contract-creation metadata, you need a query engine
    that can provide it, such as the ``ape-etherscan`` plugin
    or a node connected to the OTS namespace.
    """

    txn_hash: str
    """
    The transaction hash of the deploy transaction.
    """

    block: int
    """
    The block number of the deploy transaction.
    """

    deployer: AddressType
    """
    The contract deployer address.
    """

    factory: Optional[AddressType] = None
    """
    The address of the factory contract, if there is one
    and it is known (depends on the query provider!).
    """

    @property
    def receipt(self) -> ReceiptAPI:
        """
        The deploy transaction :class:`~ape.api.transactions.ReceiptAPI`.
        """
        return self.chain_manager.get_receipt(self.txn_hash)

    @classmethod
    def from_receipt(cls, receipt: ReceiptAPI) -> "ContractCreation":
        """
        Create a metadata class.

        Args:
            receipt (:class:`~ape.api.transactions.ReceiptAPI`): The receipt
              of the deploy transaction.

        Returns:
            :class:`~ape.api.query.ContractCreation`
        """
        return cls(
            txn_hash=receipt.txn_hash,
            block=receipt.block_number,
            deployer=receipt.sender,
            # factory is not detected since this is meant for eoa deployments
        )


class ContractEventQuery(_BaseBlockQuery):
    """
    A ``QueryType`` that collects members from ``event`` over a range of
    logs emitted by ``contract`` between ``start_block`` and ``stop_block``.
    """

    contract: Union[list[AddressType], AddressType]
    event: EventABI
    search_topics: Optional[dict[str, Any]] = None


class ContractMethodQuery(_BaseBlockQuery):
    """
    A ``QueryType`` that collects return values from calling ``method`` in ``contract``
    over a range of blocks between ``start_block`` and ``stop_block``.
    """

    contract: AddressType
    method: MethodABI
    method_args: dict[str, Any]


class QueryAPI(BaseInterface):
    @abstractmethod
    def estimate_query(self, query: QueryType) -> Optional[int]:
        """
        Estimation of time needed to complete the query. The estimation is returned
        as an int representing milliseconds. A value of None indicates that the
        query engine is not available for use or is unable to complete the query.

        Args:
            query (``QueryType``): Query to estimate.

        Returns:
            Optional[int]: Represents milliseconds, returns ``None`` if unable to execute.

        """

    @abstractmethod
    def perform_query(self, query: QueryType) -> Iterator:
        """
        Executes the query using best performing ``estimate_query`` query engine.

        Args:
            query (``QueryType``): query to execute

        Returns:
            Iterator
        """

    def update_cache(self, query: QueryType, result: Iterator[BaseInterfaceModel]):
        """
        Allows a query plugin the chance to update any cache using the results obtained
        from other query plugins. Defaults to doing nothing, override to store cache data.

        Args:
            query (``QueryType``): query that was executed
            result (``Iterator``): the result of the query
        """
