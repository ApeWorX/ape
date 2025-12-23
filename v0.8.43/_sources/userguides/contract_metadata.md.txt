# Contract Creation Metadata

Ape provides powerful contract creation metadata capabilities that reveal deployment details like deployer address, transaction hash, block number, and factory information.
This data enables contract verification, historical analysis, and audit workflows.

## Accessing Creation Metadata

Every contract instance in Ape exposes creation information through the `creation_metadata` property, which returns a `ContractCreation` object:

```python
from ape import Contract, project, accounts

# For newly deployed contracts
account = accounts.load("my-account")
contract = project.MyContract.deploy(sender=account)
metadata = contract.creation_metadata

# For existing contracts
existing_contract = Contract("0x123abc...")
metadata = existing_contract.creation_metadata
```

## Metadata Properties and Usage

The `ContractCreation` object exposes several key properties:

```python
# Deployment transaction hash
txn_hash = metadata.txn_hash

# Deployment block number - useful for historical analysis
block_number = metadata.block

# Contract deployer address - useful for ownership verification
deployer_address = metadata.deployer

# Factory contract address (for factory-deployed contracts)
factory_address = metadata.factory  # None for direct deployments

# Complete deployment transaction receipt
receipt = metadata.receipt  # See transactions guide for receipt properties
```

For complete details about transaction receipts, see the [transactions guide](./transactions.html).

These properties unlock valuable workflows such as:

```python
# Verify contract ownership
def is_creator(contract, address) -> bool:
    """Check if an address is the creator of a contract"""
    metadata = contract.creation_metadata
    return metadata and metadata.deployer == address

# Historical queries at contract inception
creation_block = contract.creation_metadata.block
initial_balance = contract.balance(block_number=creation_block)
```

## Metadata Access Implementation

Ape uses a sophisticated fallback system to retrieve contract creation metadata through several methods:

### In-Session Deployments

Contracts deployed in the current Ape session have their metadata automatically captured in memory.
This approach provides instantaneous access with zero configuration but only works for contracts deployed during the active session.

### Otterscan API Integration

For nodes with [Otterscan extensions](https://docs.otterscan.io/api-docs/ots-api), Ape utilizes the `ots_getContractCreator` RPC endpoint to obtain precise creation information.
This method offers complete data including factory details but requires a specially configured node with Otterscan functionality.

### Archive Node Deployment Detection

When working with archive nodes, Ape employs a binary search technique with `eth_getCode` to identify the deployment block, then uses block tracing (`debug_traceBlockByNumber` or `trace_replayBlockTransactions`) to reconstruct the deployment.
This approach works with many Ethereum clients but requires archive node access and performs slower than other methods.

### Explorer API Fallback

As a final option, Ape can query blockchain explorers using plugins like `ape-etherscan`.
This approach offers broad compatibility across most networks with explorers but depends on third-party services, API keys, and may lack complete factory information.

Ape intelligently attempts these methods in sequence, moving to the next if one fails.
If all methods fail, `creation_metadata` returns `None`:

```python
metadata = contract.creation_metadata
if metadata:
    print(f"Contract deployed by {metadata.deployer} in block {metadata.block}")
else:
    print("Creation metadata unavailable")
```

## Metadata Caching

To optimize performance, Ape automatically caches creation metadata.
For permanent networks (not local or fork networks), this data persists on disk for future sessions, eliminating repeated lookup overhead.

## Advanced Programmatic Access

For specialized use cases, you can work directly with the contracts cache manager:

```python
from ape import chain
from ape.api.query import ContractCreation

# Retrieve metadata programmatically
address = "0x123abc..."
metadata = chain.contracts.get_creation_metadata(address)

# Store custom metadata
chain.contracts.cache_contract_creation(
    address, 
    ContractCreation(
        txn_hash="0xabc...",
        block=12345,
        deployer="0xdef...",
        factory=None
    )
)
```

This level of access is particularly valuable for governance verification systems, contract audit tooling, and detailed deployment reporting.
