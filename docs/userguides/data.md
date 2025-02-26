# Querying Data

Ape has advanced features for querying large amounts of on-chain data.
Ape provides this support through a number of standardized methods for working with data,
routed through our query management system, which incorporates data from many sources in
your set of installed plugins.

## Getting Block Data

Use `ape console` to connect to a network:

```bash
ape console --network ethereum:mainnet:infura
```

Run block queries:

```python
# Query the first 20 blocks with all fields
df = chain.blocks.query("*", stop_block=20)

# Get specific fields from blocks
df = chain.blocks.query("number,timestamp,gas_used", start_block=16_000_000, stop_block=16_000_100)

# Access individual blocks
latest_block = chain.blocks[-1]
previous_block = chain.blocks[-2]

# Access transactions in a block
transactions = previous_block.transactions
```

## Getting Account Transaction Data

Each account within Ape fetches and stores transactional data that you can query.
To work with an account's transaction history:

```python
from ape import accounts, chain

# Query by ENS name
total_value = chain.history["example.eth"].query("value").sum()  # All value sent by this address

# Query by account object
acct = accounts.load("harambe")
tx = acct.history[-1]  # Last transaction `harambe` made

# Sum total fees paid
fees_paid = acct.history.query("total_fees_paid").sum()  # Sum of ether paid for fees
```

## Getting Contract Event Data

On a deployed contract, you can query event history:

```python
# Query all fields from a specific event
df = contract_instance.FooHappened.query("*")

# Query specific event fields
df = contract_instance.Transfer.query("from_,to,value", start_block=-1000)

# Filter high-value transfers (example with ERC-20 token)
high_value_transfers = contract_instance.Transfer.query("from_,to,value").query("value > 1000000")

# Query by block range
events = contract_instance.FooHappened.query("*", start_block=15_000_000, stop_block=15_100_000)
```

Where `contract_instance` is the return value of `owner.deploy(MyContract)` or `Contract("0x...")`

See [this guide](../userguides/contracts.html) for more information on how to deploy or load contracts.

## Using the Cache

The cache system allows you to store blockchain data locally for faster access during analysis.

```{note}
This is in Beta release.
This functionality is in constant development and many features are in planning stages.
Use the cache plugin to store provider data in a sqlite database.
```

To use the cache, first initialize it for each network you plan on caching data for:

```bash
ape cache init --network <ecosystem-name>:<network-name>
```

```{note}
Caching only works for permanently available networks. 
It will not work with local development networks.
```

For example, to initialize the cache database for the Ethereum mainnet network:

```bash
ape cache init --network ethereum:mainnet
```

This creates a SQLite database file in ape's data folder inside your home directory.

### Cache Management

You can manage your cache with these commands:

```bash
# View cache status
ape cache status --network ethereum:mainnet

# Clear specific data type from cache
ape cache clear blocks --network ethereum:mainnet

# Sync recent data to cache
ape cache sync --network ethereum:mainnet
```

The cache database has the following tables:

| Table Name        | Dataclass base | Description                   |
| ----------------- | -------------- | ----------------------------- |
| `blocks`          | `BlockAPI`     | Block headers and metadata    |
| `transactions`    | `ReceiptAPI`   | Transaction receipts and data |
| `contract_events` | `ContractLog`  | Decoded contract events       |

### Query Performance with Cache

Once cached, querying becomes much faster:

```python
# First-time query might be slow as it populates cache
df = contract.Transfer.query("*", start_block=16_000_000, stop_block=16_001_000)

# Subsequent queries using the same data are near-instantaneous
filtered = df[df['value'] > 1000000]
```
