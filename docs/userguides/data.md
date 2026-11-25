# Querying Data

`.query` is Ape's opt-in for working with larger amounts of on-chain data.
The rest of Ape, including testing, does not need a dataframe library.
Calling `.query` uses whichever [Narwhals](https://narwhals-dev.github.io/narwhals/)-supported library is already installed.
Polars is preferred when more than one is present, then pandas, PyArrow, Modin, and cuDF.
The result is a Narwhals `DataFrame`.
Select columns with brackets, as in `df["gas_used"].sum()`.
Protocol SDKs can do the same without pinning a specific library that is needed.

Nothing is imported until `.query` runs.
If no library is installed, `.query` raises `QueryEngineError` and tells you to install one.
Pass `backend=` to select a specific library for that call.
`query.backend` in `ape-config.yaml` will configure the backend for every call as a fallback.
`DataFrame.to_native()` returns the underlying object when you want to use it.

```python
df = chain.blocks.query("number,gas_used", stop_block=20)
total_gas = df["gas_used"].sum()
```

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
total_gas = df["gas_used"].sum()

# Access individual blocks
latest_block = chain.blocks[-1]
previous_block = chain.blocks[-2]

# Access transactions in a block
transactions = previous_block.transactions
```

## Getting Account Transaction Data

Each account within Ape fetches and stores transactional data that you can query.
Indexing and iteration do not use a dataframe library. `.query` does.

```python
from ape import accounts, chain

# All value sent by this address
total_value = chain.history["example.eth"].query("value")["value"].sum()

# Last transaction an account made
acct = accounts.load("harambe")
tx = acct.history[-1]

# Sum of ether paid for fees
fees_paid = acct.history.query("total_fees_paid")["total_fees_paid"].sum()
```

## Getting Contract Event Data

On a deployed contract, you can query event history. A protocol SDK can build
an index this way, for example to answer a liquidity question, and keep using
Narwhals operations on the result.

```python
# Query all fields from a specific event
df = contract_instance.FooHappened.query("*")

# Query specific event fields
df = contract_instance.Transfer.query("from_,to,value", start_block=-1000)

# Filter high-value transfers (example with ERC-20 token)
high_value_transfers = df.filter(df["value"] > 1_000_000)

# Query by block range
events = contract_instance.FooHappened.query("*", start_block=15_000_000, stop_block=15_100_000)
```

Where `contract_instance` is the return value of `owner.deploy(MyContract)` or `Contract("0x...")`

See [this guide](../userguides/contracts.html) for more information on how to deploy or load contracts.
