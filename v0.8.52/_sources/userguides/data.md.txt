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
