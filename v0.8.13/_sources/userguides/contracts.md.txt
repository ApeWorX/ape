# Contracts

You can interact with contracts pythonically using ape!
First, we need to obtain a contract instance.
One way to do this is to deploy a contract.
The other way is to initialize an already-deployed contract using its address.

## From Deploy

Deploy contracts from your project using the `project` root-level object.
You deploy contracts using Python functions such as [AccountAPI.deploy](../methoddocs/api.html#ape.api.accounts.AccountAPI.deploy) or [ContractContainer.deploy](../methoddocs/contracts.html#ape.contracts.base.ContractContainer.deploy).

```{note}
You can run Ape's deploy functions anywhere you run Python!
```

You need both an account and a contract in order to deploy a contract, as the deployment process requires a transaction to submit the contract data to the blockchain.
To learn about accounts and how to use them, see the [Accounts Guide](./accounts.html).
You also need the contract.
You can access contract types from Ape's root-level `project` object (e.g. `project.MyContract`) and their types are [ContractContainer](../methoddocs/contracts.html#ape.contracts.base.ContractContainer).

Let's assume you have a Vyper contract like this:

```vyper
contract MySmartContract:
    owner: public(address)
    balance: public(uint256)

    @public
    @payable
    @public
    def __init__(arg1: uint256, arg2: address):
        self.owner = arg2
        self.balance = arg1
```

Before you can deploy this contract, you must ensure it was compiled.
To learn about compiling in Ape, please see [this guide](./compile.html).

After it is compiled, you can deploy it.
Here is a basic example of Python code to deploy a contract:

```python
from ape import accounts, project

# You need an account to deploy, as it requires a transaction.
account = accounts.load("<ALIAS>")  # NOTE: <ALIAS> refers to your account alias!
contract = project.MyContract.deploy(1, account, sender=account)

# NOTE: You can also do it this way:
contract2 = account.deploy(project.MyContract, 1, account)
```

The arguments to the constructor (`1, account`) can be in Python form.
Ape will automatically convert values in your transactions, thus allowing you to provide higher-level objects or abstractions as input types.
That is why, as you can see, the second argument is an `AccountAPI` object for the type `address` in the contract.

Notice in the example, we use `project.MyContract` to access the contract type.
To avoid naming collisions with other properties on the `project` object, you can alternatively use the [get_contract()](../methoddocs/managers.html#ape.managers.project.manager.ProjectManager.get_contract) method to retrieve contract containers.

```python
from ape import project

contract = project.get_contract("MyContract")  # Same as `project.MyContract`.
```

Notice when deploying, we have to specify the `sender=` kwarg because `deploy` operations are transactions.
To learn more about contract interaction via transactions, see the [Contract Interaction](#contract-interaction) section below and the [guide on transactions](./transactions.html).

### Deploy Scripts

Often time, the deployment process may be unique or complex.
Or possibly, you need to run the deploy-logic from CI or in a repeatable fashion.
Or perhaps, you just want to avoid having to invoking Python directly.
In those cases, you can use Ape's scripting system to save time and store your deployment logic.
Simply copy your Python logic into an Ape script and run it via:

```shell
ape run <my-deploy-script>
```

Learn how to do this and scripting in its entirety by reviewing [the scripting user-guide](./scripts.html).

**There is no root `ape` command to deploy contracts; only the scripting-system, the `console`, or merely using Ape as a Python library**.

If your deployment process is simple or only needs to happen once, it is easy to use `ape console` to achieve a deployment.
More information on how to use `ape console` can be found [here](./console.html).

### Publishing

You can also publish the contract source code to an explorer upon deployment using the `publish=` kwarg on the deploy methods.
More information on publishing contracts can be found in [this guide](./publishing.html).

## From Project Contract Address

You can also use the [at() method](../methoddocs/contracts.html#ape.contracts.base.ContractContainer.at) from the same top-level project manager when you know the address of an already-deployed contract:

```python
from ape import project

contract = project.MyContract.at("0x68b3465833fb72A70ecDF485E0e4C7bD8665Fc45")
```

## From Any Address

If you already know the address of a contract, you can create instances of it using the `Contract` top-level factory:

```python
from ape import Contract

contract = Contract("0x68b3465833fb72A70ecDF485E0e4C7bD8665Fc45")
```

It will fetch the `contract-type` using the explorer plugin from the active network, such as [ape-etherscan](https://github.com/ApeWorX/ape-etherscan).

If you have the [ENS plugin](https://github.com/ApeWorX/ape-ens) installed, you can use `.eth` domain names as the argument:

```python
from ape import Contract

contract = Contract("v2.registry.ychad.eth")
```

## From ABIs

You can load contracts using their ABIs:

```python
from ape import Contract

address = "0x68b3465833fb72A70ecDF485E0e4C7bD8665Fc45"

# Using a JSON str:
contract = Contract(
    address, abi='[{"name":"foo","type":"fallback", "stateMutability":"nonpayable"}]'
)

# Using a JSON file path:
contract = Contract(address, abi="abi.json")

# Using a Python dictionary from JSON:
contract = Contract(
    address,
    abi=[{"name":"foo","type":"fallback", "stateMutability":"nonpayable"}]
)
```

This will create the Contract instance from the given ABI.

## From Previous Deployment

Ape keeps track of your deployments for you so you can always refer back to a version that you deployed previously.
On live networks, this history of deployments is saved; on local networks, this history lasts for the duration of your script.

Let's say you previously deployed a smart contract called `MyContract` on the rinkeby test network.
You could then refer back to it like so:

```python
from ape import project, chain

def main():
  my_contract = chain.contracts.get_deployments(project.MyContract)[-1]
```

or

```python
from ape import project

def main():
  my_contract = project.MyContract.deployments[-1]
```

`my_contract` will be of type `ContractInstance`.
`get_deployments` returns a list of deployments you made of that contract type.

## Contract Interaction

Then, after you have a contract instance, you can call methods on the contract.
For example, let's say you have a Vyper contract containing some functions:

```python
wdAmount: public(uint256)

@pure
@external
def get_static_list() -> DynArray[uint256, 3]:
    return [1, 2, 3]

@external
def set_number(num: uint256):
    assert msg.sender == self.owner, "!authorized"
    self.prevNumber = self.myNumber
    self.myNumber = num

@external
@payable
def withdraw():
    self.wdAmount = msg.value
```

Notice the contract has an external pure method, an external method that modifies state, and an external payable method that also modifies state using the given `msg.value`.
In EVM languages, methods that modify state require a transaction to execute because they cost money.
Modifying the storage of a contract requires gas and thus requires a sender with enough funding.
Methods that accept value are `payable` (e.g. `msg.value` in Vyper); provide additional value (e.g. Ether) to these methods.
Contract calls, on the other hand, are read-operations and do not cost anything.
Calls are never payable.
Thus, calls do not require specifying a `sender=` in Ape.

At the RPC level, Ethereum calls are performed using the `eth_call` RPC and transactions are performed using the `eth_sendTransaction` or `eth_sendRawTransaction` RPCs.

The following sub-sections show how, using Ape, we can invoke or call the methods defined above.

### Transactions

The following example demonstrates invoking a contract's method in Ape as a transaction.
Remember: transactions cost money, whether they are payable or not.
Payable transactions cost more money, because the contract-logic requires additional value (e.g. Ether) to be forwarded with the call.

Before continuing, take note that there is a [separate guide](./transactions.html) which fully covers transactions in Ape at a more granular level.
For this guide, assume we are using the default transaction type in Ape for Ethereum-based networks.

```python
from ape import accounts, Contract

account = accounts.load("<ALIAS>")
contract = Contract("0x...")  # Assume is deployed version of code above

# Transaction: Invoke the `set_number()` function, which costs Ether
receipt = contract.set_number(sender=account)
assert not receipt.failed

# The receipt contains data such as `gas_used`.
print(receipt.gas_used)
```

To provider additional value to a payable method, use the `value=` kwarg:

```python
receipt = contract.withdraw(sender=account, value=123)
print(receipt.gas_used)

# NOTE: You can also use "smart" values such as `"0.1 ether"` or `"100 gwei"`:
_ = contract.withdraw(sender=account, value="0.1 ether")
_ = contract.withdraw(sender=account, value="100 gwei")
_ = contract.withdraw(sender=account, value="1 wei")
```

Notice that transacting returns a [ReceiptAPI](../methoddocs/api.html#ape.api.transactions.ReceiptAPI) object which contains all the receipt data, such as `gas_used`.

```{note}
If you need the `return_value` from a transaction, you have to either treat transaction as a call (see the section below!) or use a provider with tracing-features enabled (such as `ape-foundry` or `ape-node`) and access the [return_value](../methoddocs/api.html#ape.api.transactions.ReceiptAPI.return_value) property on the receipt.
```

```python
assert receipt.return_value == 123
```

Transactions may also fail, known as a "revert".
When a transaction reverts, Ape (by default) raises a subclass of `TransactionError`, which is a Python exception.
To learn more reverts, see the [reverts guide](./reverts.html).

For more general information on transactions in the Ape framework, see [this guide](./transactions.html).

### Calls

In the Vyper code at the beginning of this section, the function `get_static_list()` is decorated as `@pure` indicating that it's read-only.
(Also in Vyper, `@view` methods are read-only).
Since `get_static_list()` is read-only, we can successfully call it without a `sender=` kwarg; no funds are required.
Here is an example of making a call by checking the result of `get_static_list()`:

```python
from ape import accounts, Contract

account = accounts.load("<ALIAS>")
contract = Contract("0x...")

# CALL: A sender is not required for calls!
assert contract.get_static_list() == [1, 2, 3]
```

### Calling Transactions and Transacting Calls

You can treat transactions as calls and vice-versa.

For example, let's say we have a Solidity function:

```solidity
function addBalance(uint256 new_bal) external returns(uint256) {
    balances[msg.sender] = new_bal;
    return balances[msg.sender];
}
```

To simulate the transaction without actually modifying any state, use the `.call` method from the contract transaction handler:

```python
from ape import Contract

contract = Contract("0x...")

result = contract.addBalance.call(123)
assert result == "123"  # The return value gets forwarded from the contract.
```

Similarly, you may want to measure a call as if it were a transaction, in which case you can use the `.transact` attribute on the contract call handler:

Given the Solidity function:

```solidity
function getModifiedBalance() external view returns(uint256) {
    return balances[msg.sender] + 123;
}
```

You can treat it like a transaction by doing:

```python
from ape import accounts, Contract

account = accounts.load("<ALIAS>")
contract = Contract("0x...")

receipt = contract.getModifiedBalance.transact(sender=account)
assert not receipt.failed  # Transactions return `ReceiptAPI` objects.
print(receipt.gas_used)  # Analyze receipt gas from calls.
```

### Default, Fallback, and Direct Calls

To directly call an address, such as invoking a contract's `fallback` or `receive` method, call a contract instance directly:

```python
from ape import Contract, accounts

sender = accounts.load("<ALIAS>")  # NOTE: <ALIAS> refers to your account alias!
contract = Contract("0x123...")

# Call the contract's fallback method.
receipt = contract(sender=sender, gas=40000, data="0x123")
```

### Private Transactions

If you are using a provider that allows private mempool transactions, you are able to use the `private=True` kwarg to publish your transaction into a private mempool.
For example, EVM providers likely will use the `eth_sendPrivateTransaction` RPC to achieve this.

To send a private transaction, do the following:

```python
receipt = contract.set_number(sender=dev, private=True)
```

The `private=True` is available on all contract interactions.

## Decoding and Encoding Inputs

If you want to separately decode and encode inputs without sending a transaction or making a call, you can achieve this with Ape.
If you know the method you want to use when decoding or encoding, you can call methods `encode_input()` or `decode_input()` on the method handler from a contract:

```python
from ape import Contract

# HexBytes(0x3fb5c1cb00000000000000000000000000000000000000000000000000000000000000de)
contract = Contract("0x...")
bytes_value = contract.my_method.encode_input(0, 1, 2)
```

In the example above, the bytes value returned contains the method ID selector prefix `3fb5c1c`.
Alternatively, you can decode input:

```python
from eth_pydantic_types import HexBytes
from ape import Contract

contract = Contract("0x...")
selector_str, input_dict = contract.my_method.decode_input(HexBytes("0x123..."))
```

In the example above, `selector_str` is the string version of the method ID, e.g. `my_method(unit256,uint256)`.
The input dict is a mapping of input names to their decoded values, e.g `{"foo": 2, "owner": "0x123..."}`.
If an input does not have a name, its key is its stringified input index.

If you don't know the method's ABI and you have calldata, you can use a `ContractInstance` or `ContractContainer` directly:

```python
import ape

# Fetch a contract
contract = ape.Contract("0x...")

# Alternative, use a contract container from ape.project
# contract = ape.project.MyContract

# Only works if unique amount of args.
bytes_value = contract.encode_input(0, 1, 2, 4, 5)
method_id, input_dict = contract.decode_input(bytes_value)
```

## Contract Interface Introspection

There may be times you need to figure out ABI selectors and method or event identifiers for a contract.
A contract instance provides properties to make this easy.
For instance, if you have a 4-byte hex method ID, you can return the ABI type for that method:

```python
import ape

usdc = ape.Contract("0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48")

# ABI type for a hex method ID
assert usdc.identifier_lookup['0x70a08231'].selector == 'balanceOf(address)'

# Also, selectors from method and event signatures
assert usdc.selector_identifiers["balances(address)"] == "0x27e235e3"

# Or dump all selectors and IDs
for identifier, abi_type in usdc.identifier_lookup.items():
    print(identifier, abi_type)
    # 0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef type='event' name='Transfer' inputs=...
    # ...
```

These include methods and error IDs, as well as event topics.

## Multi-Call and Multi-Transaction

The `ape_ethereum` core plugin comes with a `multicall` module containing tools for interacting with the [multicall3 smart contract](https://github.com/mds1/multicall).
Multicall allows you to group function calls and transactions into a single call or transaction.

Here is an example of how you can use the multicall module:

```python
import ape
from ape_ethereum import multicall

ADDRESSES = ("0xF4b8A02D4e8D76070bD7092B54D2cBbe90fa72e9", "0x80067013d7F7aF4e86b3890489AcAFe79F31a4Cb")
POOLS = [ape.project.IPool.at(a) for a in ADDRESSES]

def main():
    # Use multi-call.
    call = multicall.Call()
    for pool in POOLS:
        call.add(pool.getReserves)

    print(list(call()))

    # Use multi-transaction.
    tx = multicall.Transaction()
    for pool in POOLS:
        tx.add(pool.ApplyDiscount, 123)

    acct = ape.accounts.load("signer")
    for result in tx(sender=acct):
        print(result)
```
