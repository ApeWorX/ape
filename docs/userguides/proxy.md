# Proxy Contracts

Ape is able to detect proxy contracts so that it uses the target interface when interacting with a contract.
The following proxies are supported in `ape-ethereum`:

| Proxy Type   | Short Description                   |
| ------------ | ----------------------------------- |
| Minimal      | EIP-1167                            |
| Standard     | EIP-1967                            |
| Beacon       | EIP-1967                            |
| UUPS         | EIP-1822                            |
| Vyper        | vyper \<0.2.9 create_forwarder_to() |
| Clones       | 0xsplits clones                     |
| Safe         | Formerly Gnosis Safe                |
| OpenZeppelin | OZ Upgradable                       |
| Delegate     | EIP-897                             |
| ZeroAge      | A minimal proxy                     |
| SoladyPush0  | Uses PUSH0                          |

## Automatic Proxy Detection

Proxy detection occurs when attempting to retrieve contract types in Ape.
Ape uses various sources to find contract types, such as explorer APIs.
See [this guide](./contracts.html) to learn more about initializing contracts.

```python
from ape import Contract

# Automatic proxy detection (default behavior)
my_contract = Contract("0x...")
```

Ape will check the address you give it and detect if it hosts a proxy contract.
In the case where it determines the address is a proxy contract, it resolves the address of the implementation (every proxy is different) and returns the interface for the implementation contract.
This allows you to still call methods as you normally do on proxy contracts.

```python
# `my_contract` address points to a proxy with no methods in the interface
# However, Ape detected the implementation type and can find methods to call that way.
my_contract.my_method(sender=account)
```

## Manual Proxy Configuration

If you need more control over proxy behavior, you can manually specify proxy information when creating contract instances with `ContractContainer.at()`:

```python
from ape import project
from ape.api.networks import ProxyInfoAPI
from ape_ethereum.proxies import ProxyInfo, ProxyType

# Create proxy info with implementation address
proxy_info = ProxyInfo(target="0x1234567890123456789012345678901234567890", type=ProxyType.STANDARD)

# Create contract instance with manual proxy configuration
contract = project.MyImplementation.at(
    "0xProxyAddress",
    # Provide proxy information manually
    proxy_info=proxy_info,
)

# Or disable proxy detection entirely if you know it's not a proxy
contract = project.MyContract.at(
    "0xAddress",
    detect_proxy=False
)
```

You can also use the `Contract` factory with proxy parameters:

```python
from ape import Contract

# Disable proxy detection
contract = Contract("0xAddress", detect_proxy=False)

# Provide custom proxy info
contract = Contract(
    "0xProxyAddress", 
    proxy_info=ProxyInfoAPI(
        target="0xImplementationAddress", 
        type_name=ProxyType.STANDARD
    )
)
```

This is particularly useful when:

1. Automatic detection fails to identify a proxy contract
2. You want to force a specific implementation address
3. You're working with a custom or unusual proxy pattern
