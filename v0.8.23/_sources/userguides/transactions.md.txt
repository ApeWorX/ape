# Transactions

Regardless of how you are using `ape`, you will likely be making transactions.
There are various types of transactions you can make with `ape`. A simple example is deploying a contract.

## Transfer

One of the simplest ways to transact in Ape is to use the [the transfer method](../methoddocs/api.html?highlight=accountapi#ape.api.accounts.AccountAPI.transfer).
Transfers are transactions that send the base-currency (e.g. Ether) from one account to another.

The following is a simple guide to transferring ETH.

First, launch an ape console to your network of choice (for demo purposes; transfers can happen in any Python medium):

```shell
ape console --network ethereum:mainnet:node
```

Then, load the account you want to send money from:

```shell
account = accounts.load("<my-account>")
```

Find the address you want to send money to and invoke the `.transfer()` method.
The first argument is the account you are sending money to.
The second argument is the amount you want to send.
Any additional kwargs are passed to the transaction, such as `gas`, `max_fee`, or `max_priority_fee`, etc:

```shell
other_account = "0xab5801a7d398351b8be11c439e05c5b3259aec9b"
tx = account.transfer(other_account, "1 ETH", gas=21000)
print(tx.confirmed)
```

Learn more about accounts (necessary for `.transfer()`) by following the [Accounts Guide](./accounts.html).

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
    # Assume you have a contract named `MyContract` in your project's contracts folder.
    return account.deploy(project.MyContract)
```

### Deployment from Ape Console

Deploying from [ape console](./console.html) allows you to interact with a contract in real time. You can also use the `--network` flag to connect a live network.

```bash
ape console --network ethereum:sepolia:alchemy
```

This will launch an IPython shell:

```python
In [1]: dev = accounts.load("dev")
In [2]: token = dev.deploy(project.Token)
In [3]: token.contract_method_defined_in_contract()
```

For an in depth tutorial on how to deploy, please visit [ApeAcademy](https://academy.apeworx.io/).

### Deployment Metadata

To get the receipt of a `deploy` transaction, use the [ContractInstance.creation_metadata](../methoddocs/contracts.html#ape.contracts.base.ContractInstance.creation_metadata) property:

```{note}
Use `ape-etherscan` or a node with Otterscan for increased support for these features.
```

```python
from ape import accounts, project

dev = accounts.load("dev")
contract = project.MyContract.deploy(sender=dev)

# The receipt is available on the contract instance and has the expected sender.
receipt = contract.creation_metadata.receipt
assert receipt.sender == dev
```

**NOTE**: The `creation_metadata` contains other information as well, such as `.factory` for factory-deployed contracts.

## Dynamic-Fee Transactions

Before [EIP-1559](https://eips.ethereum.org/EIPS/eip-1559), all transactions used a `gas_price`.
After the London fork of Ethereum, the `gas_price` got broken up into two values, `max_fee` and `max_priority_fee`.
The `ape` framework supports both types of transactions. By default, transactions use the dynamic-fee model.
Making contract calls without specifying any additional `kwargs` will use a dynamic-fee transaction.

Calling certain methods on a deployed-contract is one way to transact.

```python
contract = deploy()  # Example from above, that returns a contract instance.
contract.fundMyContract(value="1 gwei", sender=sender)  # Assuming there is a method named 'fundMyContract' on MyContract.
```

In the example above, the call to `fundMyContract()` invokes a dynamic-fee transaction.
To have more control of the fee-values, you can specify the `max_fee`, the `max_priority_fee`, or both.

```python
contract.fundMyContract(value="1 gwei", max_priority_fee="50 gwei", max_fee="100 gwei", sender=sender)
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
contract.startAuction(gas_price="100 gwei", sender=sender)
```

```{note}
Miners prioritize static-fee transactions based on the highest `gas_price`.
```

Another way to use a static-fee transaction (without having to provide `gas_price`) is to set the key-value
argument `type` equal to `0x00`.

```python
contract.startAuction(type="0x0", sender=sender)
```

When declaring `type="0x0"` and _not_ specifying a `gas_price`, the `gas_price` gets set using the provider's estimation.

## Access List Transactions

Utilizing [EIP-2930](https://eips.ethereum.org/EIPS/eip-2930), you can also make access-list transactions using Ape.
Access-list transactions are static-fee transactions except you can optionally specify an access list.
Access-lists make contract-interaction more predictable and optimized.
You can also use Access-lists in Dynamic-fee transactions.

To automatically use access-list (type 1) transactions in Ape, specify `type=1` in your call:

```python
contract.startAuction(type=1, sender=sender)
```

When specifying `type=1`, Ape uses `eth_createAccessList` RPC to attach an access list to the transaction automatically.

You can also specify the access-list directly:

```python
contract.fundMyContract(type=1, sender=sender, access_list=MY_ACCESS_LIST)
```

## Payable Transactions

To add value to a transaction, use the `value=` kwarg when transacting in Ape.

```python
contract.fundMyContract(value="1 ether", sender=sender)
```

The `value="1 ether"` part is sending 1 ETH to the contract.
You would do this if `fundMyContract` was a `"payable"` method, e.g. marked `@payable` in Vyper.

## Transaction Logs

In Ape, you can easily get all the events on a receipt.
Use the `.events` property to access the ([ContractLog](../methoddocs/types.html#ape.types.ContractLog)) objects.
Each object represents an event emitted from the call.

```python
receipt = contract.fundMyContract(value="1 gwei", type="0x0", sender=sender)
print(receipt.events)
```

To only get specific log types, use the `decode_logs()` method and pass the event ABIs as arguments:

```python
for log in receipt.decode_logs(contract.FooEvent.abi, contract.BarEvent.abi):
    print(log.amount)  # Assuming 'amount' is a property on the event.
```

You can also use the [ContractEvent.from_receipt(receipt)](../methoddocs/contracts.html?highlight=contractevent#ape.contracts.base.ContractEvent.from_receipt) method:

```python
receipt = contract.fooMethod(value="1 gwei", type="0x0", sender=sender)
for log in contract.FooEvent.from_receipt(receipt):
    print(log.amount)  # Assuming 'amount' is a property on the event.
```

```{note}
If you have more than one event with the same name in your contract type's ABI, you can access the events by using the [get_event_by_signature()](../methoddocs/contracts.html?highlight=contractinstance#ape.contracts.base.ContractInstance.get_event_by_signature) method:
```

```python
event_type = contract.get_event_by_signature("FooEvent(uint256 bar, uint256 baz)")
receipt.decode_logs(event_type.abi)
```

Otherwise, you will get an `AttributeError`.

## Transaction Acceptance Timeout

```{note}
For longer running scripts, you may need to increase the transaction acceptance timeout.
```

The default value is 2 minutes for live networks and 20 seconds for local networks.
In your `ape-config.yaml` file, add the following:

```yaml
ethereum:
  mainnet:
    transaction_acceptance_timeout: 600  # 5 minutes
```

## Traces

Transaction traces are the steps in the contract the transaction took.
Traces both power a myriad of features in Ape as well are themselves a tool for developers to use to debug transactions.
To learn more about traces, see the [traces userguide](./trace.html).

## Estimate Gas Cost

To estimate the gas cost on a transaction or call without sending it, use the `estimate_gas_cost()` method from the contract's transaction / call handler:
(Assume I have a contract instance named `contract_a` that has a method named `methodToCall`)

```python
txn_cost = contract_a.myMutableMethod.estimate_gas_cost(1, sender=accounts.load("me"))
print(txn_cost)

view_cost = contract_a.myViewMethod.estimate_gas_cost()
print(view_cost)
```
