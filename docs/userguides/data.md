# Querying Data

Ape has advanced features for querying large amounts of on-chain data.
Ape provides this support through a number of standardized methods for working with data,
routed through our query management system, which incorporates data from many sources in
your set of installed plugins.

## Getting Block Data

Use `ape console`:

```bash
ape console --network ethereum:mainnet:infura
```

Run a few queries:

```python
In [1]: df = chain.blocks.query("*", stop_block=20)
In [2]: chain.blocks[-2].transactions  # List of transactions in block
```

## Getting Account Transaction Data

Each account within ape will also fetch and store transactional data that you can query.
To work with an account's transaction data, you can do stuff like this:

```python
from ape import accounts, chain

chain.history["example.eth"].query("value").sum()  # All value sent by this address
acct = accounts.load("my-acct")
tx = acct.history[-1]  # Last txn `acct` made
acct.history.query("total_fees_paid").sum()  # Sum of ether paid for fees by `acct`
```

## Getting Contract Event Data

On a deployed contract, you can query event history.

For example, we have a contract with a `FooHappened` event that you want to query from.
This is how you would query the args from an event:

```python
In [1]: df = contract_instance.FooHappened.query("*", start_block=-1)
```

where `contract_instance` is the return value of `owner.deploy(MyContract)`

See [this guide](../userguides/contracts.html) for more information how to deploy or load contracts.

## Using the Cache

```{note}
This is in Beta release.
This functionality is in constant development and many features are in planning stages.
Use the cache plugin to store provider data in a sqlite database.
```

To use the cache, first you must initialize it for each network you plan on caching data for:

```bash
ape cache init --network <ecosystem-name>:<network-name>
```

```{note}
Caching only works for permanently available networks. 
It will not work with local development networks.
```

For example, to initialize the cache database for the Ethereum mainnet network, you would do the following:

```bash
ape cache init --network ethereum:mainnet
```

This creates a SQLite database file in ape's data folder inside your home directory.

You can query the cache database directly, for debugging purposes.
The cache database has the following tables:

| Table Name        | Dataclass base |
| ----------------- | -------------- |
| `blocks`          | `BlockAPI`     |
| `transactions`    | `ReceiptAPI`   |
| `contract_events` | `ContractLog`  |
