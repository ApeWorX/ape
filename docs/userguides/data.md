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
In [1]: chain.history["example.eth"].query("value").sum()  # All value sent by this address
In [2]: acct = accounts.load("my-acct"); acct.history[-1]  # Last txn `acct` made
In [3]: acct.history.query("total_fees_paid").sum()  # Sum of ether paid for fees by `acct`
```

## Getting Contract Event Data

On a deployed contract, you can query event history:

For example, we have a contract with a `FooHappened` event that you want to query from.
This is how you would query the args from an event:

```python
contract_instance.FooHappened.query("*", start_block=-1)
```

where `contract_instance` is the return value of `owner.deploy(MyContract)`

See [this guide](../userguides/contracts.html) for more information how to deploy or load contracts.

## Using the Cache

**Note**: This is in Beta release.
This functionality is in constant development and many features are in planning stages.
Use the cache plugin to store provider data in a sqlite database.

To use the cache, first you must initialize it for each network you plan on caching data for:

```bash
ape cache init --network <ecosystem-name>:<network-name>
```

**Note**: Caching only works for permanently available networks. It will not work with local development networks.

For example, to initialize the cache database for the Ethereum mainnet network, you would do the following:

```bash
ape cache init --network ethereum:mainnet
```

This creates a SQLite database file in ape's data folder inside your home directory.

You can query the cache database directly, for debugging purposes.
For example, to get block data, you would query the `blocks` table:

```bash
ape cache query --network ethereum:mainnet:infura "SELECT * FROM blocks"
```

Which will return something like this:

```bash
                                                 hash num_transactions  number                                        parent_hash  size   timestamp  gas_limit  gas_used base_fee   difficulty  total_difficulty
0   b'\xd4\xe5g@\xf8v\xae\xf8\xc0\x10\xb8j@\xd5\xf...                0       0  b'\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00...   540           0       5000         0     None  17179869184       17179869184
1   b'\x88\xe9mE7\xbe\xa4\xd9\xc0]\x12T\x99\x07\xb...                0       1  b'\xd4\xe5g@\xf8v\xae\xf8\xc0\x10\xb8j@\xd5\xf...   537  1438269988       5000         0     None  17171480576       34351349760
2   b'\xb4\x95\xa1\xd7\xe6f1R\xae\x92p\x8d\xa4\x84...                0       2  b'\x88\xe9mE7\xbe\xa4\xd9\xc0]\x12T\x99\x07\xb...   544  1438270017       5000         0     None  17163096064       51514445824
...
```

Similarly, to get transaction data, you would query the `transactions` table:

```bash
ape cache query --network ethereum:mainnet:infura "SELECT * FROM transactions"
```

Finally, to query cached contract events you would query the `contract_events` table:

```bash
ape cache query --network ethereum:mainnet:infura "SELECT * FROM contract_events"
```
