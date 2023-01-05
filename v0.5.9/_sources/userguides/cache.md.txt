# Cache

**Note**: This is in Beta release. This functionality is in constant development and many features are in planning stages.
Use the cache plugin to store provider data in a sqlite database.\*\*

```bash
ape cache init --network <ecosystem-name>:<network-name>
```

If you want to set up your network connection for caching use [this guide](./network.html)

```bash
ape cache init --network ethereum:mainnet
```

This creates a SQLite database file in the hidden ape folder.

## Get data from the provider

Use `ape console`:

```bash
ape console --network ethereum:mainnet:infura
```

Run a few queries:

```python
In [1]: chain.blocks.query("*", stop_block=20)
In [2]: chain.blocks[-2].transactions
```

On a deployed contract, you can query events:

- Below, FooHappened is the event from your contract instance that you want to query from.

```python
contract_instance.FooHappened.query("*", start_block=-1)
```

where `contract_instance` is the return of owner.deploy(Contract)

See [this guide](../userguides/contracts.html) for more information how to get a contract instance.

Exit the IPython interpreter.

You can query the cache database directly, for debugging purposes. For example, to get the `blocks` table data from the SQLite db we can do the following:

```bash
ape cache query --network ethereum:mainnet:infura "SELECT * FROM blocks"
```

Returns:

```bash
                                                 hash num_transactions  number                                        parent_hash  size   timestamp  gas_limit  gas_used base_fee   difficulty  total_difficulty
0   b'\xd4\xe5g@\xf8v\xae\xf8\xc0\x10\xb8j@\xd5\xf...                0       0  b'\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00...   540           0       5000         0     None  17179869184       17179869184
1   b'\x88\xe9mE7\xbe\xa4\xd9\xc0]\x12T\x99\x07\xb...                0       1  b'\xd4\xe5g@\xf8v\xae\xf8\xc0\x10\xb8j@\xd5\xf...   537  1438269988       5000         0     None  17171480576       34351349760
2   b'\xb4\x95\xa1\xd7\xe6f1R\xae\x92p\x8d\xa4\x84...                0       2  b'\x88\xe9mE7\xbe\xa4\xd9\xc0]\x12T\x99\x07\xb...   544  1438270017       5000         0     None  17163096064       51514445824
```

To get `transactions` or `contract_events`:

```bash
ape cache query --network ethereum:mainnet:infura "SELECT * FROM transactions"
```

or

```bash
ape cache query --network ethereum:mainnet:infura "SELECT * FROM contract_events"
```
