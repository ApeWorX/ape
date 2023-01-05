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
    # Assume you have a contract named `MyContract` in your project's contracts folder.
    return account.deploy(project.MyContract)
```

To get the receipt of a `deploy` transaction, use the [ContractInstance.receipt](../methoddocs/contracts.html#ape.contracts.base.ContractInstance.receipt) property:

```python
from ape import accounts, project

dev = accounts.load("dev")
contract = project.MyContract.deploy(sender=dev)

# The receipt is available on the contract instance and has the expected sender.
receipt = contract.receipt
assert receipt.sender == dev
```

### Deployment from Ape Console

Deploying from [ape console](./console.html) allows you to interact with a contract in real time. You can also use the `--network` flag to connect a live network.

```bash
ape console --network ethereum:goerli:alchemy
```

This will launch an IPython shell:

```python
In [1]: dev = accounts.load("dev")
In [2]: token = dev.deploy(project.Token) 
In [3]: token.contract_method_defined_in_contract()
```

For an in depth tutorial on how to deploy, please visit [ApeAcademy](https://academy.apeworx.io/).

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
contract.fundMyContract(value="1 gwei", gas_price="100 gwei", sender=sender)
```

**NOTE**: Miners prioritize static-fee transactions based on the highest `gas_price`.

Another way to use a static-fee transaction (without having to provide `gas_price`) is to set the key-value
argument `type` equal to `0x00`.

```python
contract.fundMyContract(value="1 gwei", type="0x0", sender=sender)
```

When declaring `type="0x0"` and _not_ specifying a `gas_price`, the `gas_price` gets set using the provider's estimation.

## Transaction Logs

To get logs that occurred during a transaction, you can use the [ContractEvent.from_receipt(receipt)](../methoddocs/contracts.html?highlight=contractevent#ape.contracts.base.ContractEvent.from_receipt) and access your data from the [ContractLog](../methoddocs/types.html#ape.types.ContractLog) objects that it returns.

The following is an example demonstrating how to access logs from an instance of a contract:

```python
receipt = contract.fundMyContract(value="1 gwei", type="0x0", sender=sender)
for log in contract.MyFundEvent.from_receipt(receipt):
    print(log.amount)  # Assuming 'amount' is a property on the event.
```

You can also access the logs from the receipt itself if you know the ABI:

```python
event_type = contract.MyEvent
for log in receipt.decode_logs(event_type.abi):
    print(log.amount)  # Assuming 'amount' is a property on the event.
```

**NOTE**: If you have more than event with the same name in your contract type's ABI, you can access the events by using the [get_event_by_signature()](../methoddocs/contracts.html?highlight=contractinstance#ape.contracts.base.ContractInstance.get_event_by_signature) method:

```python
event_type = contract.get_event_by_signature("FooEvent(uint256 bar, uint256 baz)")
receipt.decode_logs(event_type.abi)
```

Otherwise, you will get an `AttributeError`.

## Transaction Acceptance Timeout

**NOTE** For longer running scripts, you may need to increase the transaction acceptance timeout.
The default value is 2 minutes for live networks and 20 seconds for local networks.
In your `ape-config.yaml` file, add the following:

```yaml
ethereum:
  mainnet:
    transaction_acceptance_timeout: 600  # 5 minutes
```

## Traces

If you are using a provider that is able to fetch transaction traces, such as the [ape-hardhat](https://github.com/ApeWorX/ape-hardhat) provider, you can call the [`ReceiptAPI.show_trace()`](../methoddocs/api.html?highlight=receiptapi#ape.api.transactions.ReceiptAPI.show_trace) method.

```python
from ape import accounts, project

owner = accounts.load("acct")
contract = project.Contract.deploy(sender=owner)
receipt = contract.methodWithoutArguments()
receipt.show_trace()
```

**NOTE**: If your provider does not support traces, you will see a `NotImplementedError` saying that the method is not supported.

The trace might look something like:

```bash
Call trace for '0x43abb1fdadfdae68f84ce8cd2582af6ab02412f686ee2544aa998db662a5ef50'
txn.origin=0x1e59ce931B4CFea3fe4B875411e280e173cB7A9C
ContractA.methodWithoutArguments() -> 0x00..7a9c [469604 gas]                                                                                                                                     
├── SYMBOL.supercluster(x=234444) -> [                                                                                                                                                            
│       [23523523235235, 11111111111, 234444],                                                                                                                                                    
│       [                                                                                                                                                                                         
│         345345347789999991,                                                                                                                                                                     
│         99999998888882,                                                                                                                                                                         
│         345457847457457458457457457                                                                                                                                                             
│       ],                                                                                                                                                                                        
│       [234444, 92222229999998888882, 3454],                                                                                                                                                     
│       [                                                                                                                                                                                         
│         111145345347789999991,                                                                                                                                                                  
│         333399998888882,                                                                                                                                                                        
│         234545457847457457458457457457                                                                                                                                                          
│       ]                                                                                                                                                                                         
│     ] [461506 gas]                                                                                                                                                                              
├── SYMBOL.methodB1(lolol="ice-cream", dynamo=345457847457457458457457457) [402067 gas]                                                                                                           
│   ├── ContractC.getSomeList() -> [                                                                                                                                                              
│   │     3425311345134513461345134534531452345,                                                                                                                                                  
│   │     111344445534535353,                                                                                                                                                                     
│   │     993453434534534534534977788884443333                                                                                                                                                    
│   │   ] [370103 gas]                                                                                                                                                                            
│   └── ContractC.methodC1(                                                                                                                                                                       
│         windows95="simpler",                                                                                                                                                                    
│         jamaica=345457847457457458457457457,                                                                                                                                                    
│         cardinal=ContractA                                                                                                                                                                      
│       ) [363869 gas]                                                                                                                                                                            
├── SYMBOL.callMe(blue=tx.origin) -> tx.origin [233432 gas]                                                                                                                                       
├── SYMBOL.methodB2(trombone=tx.origin) [231951 gas]                                                                                                                                              
│   ├── ContractC.paperwork(ContractA) -> (                                                                                                                                                       
│   │     os="simpler",                                                                                                                                                                           
│   │     country=345457847457457458457457457,                                                                                                                                                    
│   │     wings=ContractA                                                                                                                                                                         
│   │   ) [227360 gas]                                                                                                                                                                            
│   ├── ContractC.methodC1(windows95="simpler", jamaica=0, cardinal=ContractC) [222263 gas]                                                                                                       
│   ├── ContractC.methodC2() [147236 gas]                                                                                                                                                         
│   └── ContractC.methodC2() [122016 gas]                                                                                                                                                         
├── ContractC.addressToValue(tx.origin) -> 0 [100305 gas]                                                                                                                                         
├── SYMBOL.bandPractice(tx.origin) -> 0 [94270 gas]                                                                                                                                               
├── SYMBOL.methodB1(lolol="lemondrop", dynamo=0) [92321 gas]                                                                                                                                      
│   ├── ContractC.getSomeList() -> [                                                                                                                                                              
│   │     3425311345134513461345134534531452345,                                                                                                                                                  
│   │     111344445534535353,                                                                                                                                                                     
│   │     993453434534534534534977788884443333                                                                                                                                                    
│   │   ] [86501 gas]                                                                                                                                                                             
│   └── ContractC.methodC1(windows95="simpler", jamaica=0, cardinal=ContractA) [82729 gas]                                                                                                        
└── SYMBOL.methodB1(lolol="snitches_get_stiches", dynamo=111) [55252 gas]                                                                                                                         
    ├── ContractC.getSomeList() -> [                                                                                                                                                              
    │     3425311345134513461345134534531452345,                                                                                                                                                  
    │     111344445534535353,                                                                                                                                                                     
    │     993453434534534534534977788884443333                                                                                                                                                    
    │   ] [52079 gas]                                                                                                                                                                             
    └── ContractC.methodC1(windows95="simpler", jamaica=111, cardinal=ContractA) [48306 gas]                                                                                                      
```

Additionally, you can view the traces of other transactions on your network.

```python
from ape import networks

txn_hash = "0x053cba5c12172654d894f66d5670bab6215517a94189a9ffc09bc40a589ec04d"
receipt = networks.provider.get_receipt(txn_hash)
receipt.show_trace()
```

In Ape, you can also show the trace for a call.
Use the `show_trace=` kwarg on a contract call and Ape will display the trace before returning the data.

```python
token.balanceOf(account, show_trace=True)
```

**NOTE**: This may not work on all providers, but it should work on common ones such as `ape-hardhat` or `ape-geth`.

## Gas Reports

To view the gas report of a transaction receipt, use the [`ReceiptAPI.show_gas_report()`](../methoddocs/api.html?highlight=receiptapi#ape.api.transactions.ReceiptAPI.show_gas_report) method:

```python
from ape import networks

txn_hash = "0x053cba5c12172654d894f66d5670bab6215517a94189a9ffc09bc40a589ec04d"
receipt = networks.provider.get_receipt(txn_hash)
receipt.show_gas_report()
```

It will output tables of contracts and methods with gas usages that look like this:

```bash
                            DAI Gas

  Method           Times called    Min.    Max.    Mean   Median
 ────────────────────────────────────────────────────────────────
  balanceOf                   4   1302    13028   1302    1302
  allowance                   2   1377    1377    1337    1337
│ approve                     1   22414   22414   22414   22414
│ burn                        1   11946   11946   11946   11946
│ mint                        1   25845   25845   25845   25845
```

## Estimate Gas Cost

To estimate the gas cost on a transaction or call without sending it, use the `estimate_gas_cost()` method from the contract's transaction / call handler:
(Assume I have a contract instance named `contract_a` that has a method named `methodToCall`)

```python
txn_cost = contract_a.myMutableMethod.estimate_gas_cost(1, sender=accounts.load("me"))
print(txn_cost)

view_cost = contract_a.myViewMethod.estimate_gas_cost()
print(view_cost)
```
