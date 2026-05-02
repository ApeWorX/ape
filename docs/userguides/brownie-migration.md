# Brownie to Ape Migration

[Brownie is no longer actively maintained. The Brownie README directs Python Ethereum developers to Ape Framework.](https://github.com/eth-brownie/brownie#readme) This guide documents a practical migration path for Brownie projects moving to Ape and references [ApeWorX/ape issue #640](https://github.com/ApeWorX/ape/issues/640), which originally tracked Brownie project migration support.

## Imports

Brownie scripts often import accounts, contracts, config, and networks from `brownie`. Migrated Ape scripts import public Ape APIs and access contracts through `project`.

Brownie:

```python
from brownie import accounts, config, SimpleStorage, network
```

Ape:

```python
from ape import accounts, config, networks, project
```

## Accounts

Use `accounts.test_accounts` for local generated accounts and `accounts.load()` for named account aliases. The alias must be imported by the user before live-network use.

Brownie:

```python
if network.show_active() == "development":
    return accounts[0]

return accounts.add(config["wallets"]["from_key"])
```

Ape:

```python
if not networks.provider.network.is_dev:
    return accounts.test_accounts[0]

return accounts.load("<alias>")
```

Official docs: [Accounts](./accounts.html)

## Contract Deployment and Transactions

Brownie transaction dictionaries become explicit Ape keyword arguments such as `sender=` and `value=`.

Brownie:

```python
simple_storage = SimpleStorage.deploy({"from": account})
transaction = simple_storage.store(15, {"from": account})
```

Ape:

```python
simple_storage = project.SimpleStorage.deploy(sender=account)
transaction = simple_storage.store(15, sender=account)
```

For payable calls:

Brownie:

```python
tx = fund_me.fund({"from": account, "value": entrance_fee})
```

Ape:

```python
tx = fund_me.fund(sender=account, value=entrance_fee)
```

Official docs: [Contracts](./contracts.html)

## Networks

Brownie's active-network helper maps to Ape's active provider network metadata.

Brownie:

```python
print(f"The active network is {network.show_active()}")
```

Ape:

```python
print(f"The active network is {networks.provider.network.name}")
```

Official docs: [Networks](./networks.html)

## Testing and Reverts

Brownie revert helpers and exceptions map to Ape testing helpers and exceptions.

Brownie:

```python
with brownie.reverts("Ownable: caller is not the owner"):
    fund_me.withdraw({"from": bad_actor})
```

Ape:

```python
with ape.reverts("Ownable: caller is not the owner"):
    fund_me.withdraw(sender=bad_actor)
```

For Brownie tests catching the generic VM error exception:

Brownie:

```python
with pytest.raises(exceptions.VirtualMachineError):
    fund_me.withdraw({"from": bad_actor})
```

Ape:

```python
from ape.exceptions import ContractLogicError

with pytest.raises(ContractLogicError):
    fund_me.withdraw(sender=bad_actor)
```

Official docs: [Testing](./testing.html)

## Testing: pytest Fixtures

Ape tests use pytest fixtures from the `ape-test` plugin.
In Ape, contract types are not injected as pytest fixtures.
Use the `project` fixture and access contracts as `project.ContractName`.

Remove Brownie's `fn_isolation` fixture when migrating tests. Ape handles test isolation through its pytest plugin, so the fixture has no Ape equivalent and should be deleted.

Brownie:

```python
@pytest.fixture(autouse=True)
def isolate(fn_isolation):
    pass
```

Use Ape's `accounts` fixture with `project` for deployments:

Brownie:

```python
def test_deploy(Token, accounts):
    account = accounts[0]
    token = Token.deploy({"from": account})
```

Ape:

```python
def test_deploy(project, accounts):
    account = accounts[0]
    token = project.Token.deploy(sender=account)
```

Update contract fixture patterns the same way:

Brownie:

```python
@pytest.fixture
def token(Token, accounts):
    return Token.deploy({"from": accounts[0]})
```

Ape:

```python
@pytest.fixture
def token(project, accounts):
    return project.Token.deploy(sender=accounts[0])
```

If tests manually use chain snapshots, `chain.snapshot()` remains similar, but Brownie's `chain.revert()` should become Ape's `chain.restore()`.

Brownie:

```python
chain.snapshot()
chain.revert()
```

Ape:

```python
chain.snapshot()
chain.restore()
```

Brownie provides a `web3` pytest fixture for direct Web3.py access in tests.
Ape does not provide a `web3` fixture.

If direct Web3 access is needed, use the active provider.

Brownie:

```python
def test_block_number(web3):
    assert web3.eth.block_number >= 0
```

Ape:

```python
def test_block_number(chain):
    assert chain.provider.web3.eth.block_number >= 0
```

Official docs: [Testing](./testing.html)

## Config Files

Brownie configuration values should move into Ape's `ape-config.yaml` structure. Wallet private keys are not copied into config; import an Ape account alias instead with `ape accounts import <alias>` and use `accounts.load("<alias>")` from scripts.

Brownie (`brownie-config.yaml`):

```yaml
dependencies:
  - smartcontractkit/chainlink-brownie-contracts@1.1.1
compiler:
  solc:
    remappings:
      - "@chainlink=smartcontractkit/chainlink-brownie-contracts@1.1.1"
wallets:
  from_key: ${PRIVATE_KEY}
networks:
  development:
    verify: false
```

Ape (`ape-config.yaml`):

```yaml
name: migrated-ape-project
plugins:
  - name: solidity
solidity:
  version: 0.8.20
  import_remapping:
    - "@chainlink=smartcontractkit/chainlink-brownie-contracts@1.1.1"
ethereum:
  default_network: local
```

Official docs: [Config](./config.html)
