# Traces

A transaction's trace frames are the individual steps the transaction took.
Using traces, Ape is able to offer features like:

1. Showing a pretty call-tree from a transaction receipt
2. Gas reporting in `ape test`
3. Coverage tools in `ape test`

Some network providers, such as Alchemy and Foundry, implement `debug_traceTransaction` and Parity's `trace_transaction` affording tracing capabilities in Ape.

```{warning}
Without RPCs for obtaining traces, some features such as gas-reporting and coverage are limited.
```

To see a transaction trace, use the [show_trace()](../methoddocs/api.html#ape.api.transactions.ReceiptAPI.show_trace) method on a receipt API object.

Here is an example using `show_trace()` in Python code to print out a transaction's trace.

```{note}
This code runs assuming you are connected to `ethereum:mainnet` using a provider with tracing RPCs.
```

To learn more about networks in Ape, see the [networks guide](./networks.html).

```python
from ape import chain

tx = chain.provider.get_receipt('0xb7d7f1d5ce7743e821d3026647df486f517946ef1342a1ae93c96e4a8016eab7')

# Show the steps the transaction took.
tx.show_trace()
```

You should see a (less-abridged) trace like:

```
Call trace for '0xb7d7f1d5ce7743e821d3026647df486f517946ef1342a1ae93c96e4a8016eab7'
tx.origin=0x5668EAd1eDB8E2a4d724C8fb9cB5fFEabEB422dc
DSProxy.execute(_target=LoanShifterTaker, _data=0x35..0000) -> "" [1421947 gas]
└── (delegate) LoanShifterTaker.moveLoan(
      _exchangeData=[
        0xEeeeeEeeeEeEeeEeEeEeeEEEeeeeEeeeeeeeEEeE,
        ZERO_ADDRESS,
        
        ...
        # Abridged because is super long #
        ...
 

    │                   └── LendingRateOracle.getMarketBorrowRate(_asset=DAI) -> 
    │                       35000000000000000000000000 [1164 gas]
    ├── DSProxy.authority() -> DSGuard [1291 gas]
    ├── DSGuard.forbid(src=LoanShifterReceiver, dst=DSProxy, sig=0x1c..0000) [5253 gas]
    └── DefisaverLogger.Log(
          _contract=DSProxy, 
          _caller=tx.origin, 
          _logName="LoanShifter", 
          _data=0x00..0000
        ) [6057 gas]                                                                              
```

Similarly, you can use the provider directly to get a trace.
This is useful if you want to interact with the trace or change some parameters for creating the trace.

```python
from ape import chain

# Change the `debug_traceTransaction` parameter dictionary
trace = chain.provider.get_transaction_trace(
    "0x...", debug_trace_transaction_parameters={"enableMemory": False}
)

# You can still print the pretty call-trace (as we did in the example above)
print(trace)

# Interact with low-level logs for deeper analysis.
struct_logs = trace.get_raw_frames()
```

## Tracing Calls

Some network providers trace calls in addition to transactions.
EVM-based providers best achieve this by implementing the `debug_traceCall` RPC.

If you want to see the trace of call when making the call, use the `show_trace=` flag:

```python
token.balanceOf(account, show_trace=True)
```

```{warning}
If your provider does not properly support call-tracing (e.g. doesn't implement `debug_traceCall`), traces are limited to the top-level call.
```

Ape traces calls automatically when using `--gas` or `--coverage` in tests to build reports.
Learn more about testing in Ape in the [testing guide](./testing.html) and in the following sections.

## Gas Reports

To view the gas report of a transaction receipt, use the [ReceiptAPI.show_gas_report()](../methoddocs/api.html?highlight=receiptapi#ape.api.transactions.ReceiptAPI.show_gas_report) method:

```python
from ape import networks

txn_hash = "0x053cba5c12172654d894f66d5670bab6215517a94189a9ffc09bc40a589ec04d"
receipt = networks.provider.get_receipt(txn_hash)
receipt.show_gas_report()
```

It outputs tables of contracts and methods with gas usages that look like this:

```
                            DAI Gas

  Method           Times called    Min.    Max.    Mean   Median
 ────────────────────────────────────────────────────────────────
  balanceOf                   4   1302    13028   1302    1302
  allowance                   2   1377    1377    1337    1337
│ approve                     1   22414   22414   22414   22414
│ burn                        1   11946   11946   11946   11946
│ mint                        1   25845   25845   25845   25845
```
