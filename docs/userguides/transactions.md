# Making Transactions

Regardless of how you are using `ape`, you will likely be making transactions.
There are various types of transactions you can make with `ape`. A simple example is deploying a contract.

## Deployment

Deploying a smart contract is a unique type of transaction where we don't necessarily care about the receipt as much
as we care about the contract instance. That is why the return value from
[the deploy method](../methoddocs/api.html?highlight=accountapi#ape.api.accounts.AccountAPI.deploy) is a
[ContractInstance](../methoddocs/contracts.html?highlight=contractinstance#ape.contracts.base.ContractInstance).

The following example demonstrates a simple deployment script:

```python
from ape import accounts, project


def deploy():
    account = accounts.load("MyAccount")
    return account.deploy(project.MyContract)
```

## Dynamic-Fee Transactions

Before [EIP-1559](https://eips.ethereum.org/EIPS/eip-1559), all transactions used a `gas_price`.
After the London fork of Etheruem, the `gas_price` got broken up into two values, `max_fee` and `max_priority_fee`.
The `ape` framework supports both types of transactions. By default, transactions use the dynamic-fee model.
Making contract calls without specifying any additional `kwargs` will use a dynamic-fee transaction.

Calling certain methods on a deployed-contract is one way to transact.

```python
contract = deploy()  # Example from above, that returns a contract instance.
contract.fundMyContract(value="1 gwei")  # Assuming there is a method named 'fundMyContract' on MyContract.
```

In the example above, the call to `fundMyContract()` invokes a dynamic-fee transaction.
To have more control of the fee-values, you can specify the `max_fee`, the `max_priority_fee`, or both.

```python
contract.fundMyContract(value="1 gwei", max_priority_fee="50 gwei", max_fee="100 gwei")
```

The `max_priority_fee` cannot exceed the `max_fee`, as the `max_fee` includes both the base fee and the priority fee.
The `max_priority_fee`, when omitted, defaults to the return value from the
[ProviderAPI.priority_fee](../methoddocs/api.html?highlight=accountapi#ape.api.providers.ProviderAPI.priority_fee)
method property.
The `max_fee`, when omitted, defaults to the `priority_fee` (which gets its default applied beforehand) plus the latest
the value returned from the
[ProviderAPI.base_fee](../methoddocs/api.html?highlight=accountapi#ape.api.providers.ProviderAPI.base_fee) method
property.

## Static-Fee Transactions

Static-fee transactions are the transactions that Ethereum used before the London-fork
(before [EIP-1559](https://eips.ethereum.org/EIPS/eip-1559)).
**However, some applications may still require using static-fee transactions.**

One way to use a static-fee transaction is by specifying the `gas_price` as a key-value argument:

```python
contract.fundMyContract(value="1 gwei", gas_price="100 gwei")
```

**NOTE**: Miners prioritize static-fee transactions based on the highest `gas_price`.

Another way to use a static-fee transaction (without having to provide `gas_price`) is to set the key-value
argument `type` equal to `0x00`.

```python
contract.fundMyContract(value="1 gwei", type="0x0")
```

When declaring `type="0x0"` and _not_ specifying a `gas_price`, the `gas_price` gets set using the provider's estimation.
