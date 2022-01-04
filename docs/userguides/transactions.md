# Making Transactions

Regardless of how you are using `ape`, you will likely be making transactions. There are various types of transactions
you can make with `ape`. A simple example is deploying a contract.

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

## Dynamic Fee Transactions

Before [EIP-1559](https://eips.ethereum.org/EIPS/eip-1559)), all transactions used a `gas_price`. After the London fork
of Etheruem, the `gas_price` got broken up into two values `max_fee` and `max_priority_fee`. The `ape` platform supports
both types of transactions. By default, transactions use the dynamic fee model. Making contract calls without specifying
any additional `kwargs` will use a dynamic-fee transaction.

Calling certain methods on a deployed-contract is a way to transact.

```python
contract = deploy()  # Example from above, that returns a contract instance.
contract.fundMyContract(value="1 gwei")  # Assuming there is a method named 'fundMyContract' on MyContract.
```

In the example above, the call to `fundMyContract()` invokes a dynamic-fee transaction. To have more control of the 
fee-values, you can specify the `max_fee` and the `max_priority_fee`.

```python
contract = deploy()  # Example from above, that returns a contract instance.
contract.fundMyContract(value="1 gwei", max_priorty_fee=50000000000, max_fee=100000000000)
```

## Static Fee Transactions

To use the original static fee transactions, you can merely specify a `type="0x0"`.

```python
contract = deploy()  # Example from above, that returns a contract instance.
contract.fundMyContract(value="1 gwei", type="0x0")
```

Also, specifying a `gas_price` will automatically trigger the usage of a static-fee transaction.

```python
contract = deploy()  # Example from above, that returns a contract instance.
contract.fundMyContract(value="1 gwei", gas_price=100000000000)
```
