# Proxy Contracts

Ape is able to detect proxy contracts so that it uses the target interface when interacting with a contract.
The following proxies are supporting in `ape-ethereum`:

| Proxy Type   | Short Description                 |
| ------------ | --------------------------------- |
| Minimal      | EIP-1167                          |
| Standard     | EIP-1967                          |
| Beacon       | EIP-1967                          |
| UUPS         | EIP-1822                          |
| Vyper        | vyper \<0.2.9 create_forwarder_to |
| Clones       | 0xsplits clones                   |
| Safe         | Formerly Gnosis Safe              |
| OpenZeppelin | OZ Upgradable                     |
| Delegate     | EIP-897                           |
| ZeroAge      | A minimal proxy                   |
| SoladyPush0  | Uses PUSH0                        |

Proxy detection occurs when attempting to retrieve contract types in Ape.
Ape uses various sources to find contract types, such as explorer APIs.
See [this guide](./contracts.html) to learn more about initializing contracts.

```python
from ape import Contract

my_contract = Contract("0x...")
```

Ape will check the address you give it and detect if hosts a proxy contract.
In the case where it determines the address is a proxy contract, it resolves the address of the implementation (every proxy is different) and returns the interface for the implementation contract.
This allows you to still call methods as you normally do on proxy contracts.

```python
# `my_contract` address points to a proxy with no methods in the interface
# However, Ape detected the implementation type and can find methods to call that way.
my_contract.my_method(sender=account)
```
