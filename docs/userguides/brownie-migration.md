# Brownie to Ape Migration

[Brownie is no longer actively maintained. The Brownie README directs Python Ethereum developers to Ape Framework.](https://github.com/eth-brownie/brownie#readme) This guide documents a practical migration path for Brownie projects moving to Ape and references [ApeWorX/ape issue #640](https://github.com/ApeWorX/ape/issues/640), which originally tracked Brownie project migration support.

## Migration

### Imports

Brownie scripts often import accounts, contracts, config, and networks from `brownie`. Migrated Ape scripts import public Ape APIs and access contracts through `project`.

```python
# Before
from brownie import accounts, config, SimpleStorage, network

# After
from ape import accounts, config, networks, project
```

Official docs: [Contracts](./contracts.html)

### Accounts

Use `accounts.test_accounts` for local generated accounts and `accounts.load()` for named account aliases. The alias must be imported by the user before live-network use.

```python
# Before
if network.show_active() == "development":
    return accounts[0]
return accounts.add(config["wallets"]["from_key"])

# After
if networks.provider.network.name == "development":
    return accounts.test_accounts[0]
return accounts.add(config["wallets"]["from_key"])  # TODO(apeshift): accounts.add(key) not valid in Ape; use accounts.load("account-name") after: ape accounts import <name>
```

Official docs: [Accounts](./accounts.html)

### Contract Deployment and Transactions

Brownie transaction dictionaries become explicit Ape keyword arguments such as `sender=` and `value=`.

```python
# Before
simple_storage = SimpleStorage.deploy({"from": account})
transaction = simple_storage.store(15, {"from": account})

# After
simple_storage = project.SimpleStorage.deploy(sender=account)
transaction = simple_storage.store(15, sender=account)
```

For payable calls:

```python
# Before
tx = fund_me.fund({"from": account, "value": entrance_fee})

# After
tx = fund_me.fund(sender=account, value=entrance_fee)
```

Official docs: [Contracts](./contracts.html)

### Networks

Brownie's active-network helper maps to Ape's active provider network metadata.

```python
# Before
print(f"The active network is {network.show_active()}")

# After
print(f"The active network is {networks.provider.network.name}")
```

Official docs: [Networks](./networks.html)

### Testing and Reverts

Brownie revert helpers and exceptions map to Ape testing helpers and exceptions.

```python
# Before
with brownie.reverts("Ownable: caller is not the owner"):
    fund_me.withdraw({"from": bad_actor})

# After
with ape.reverts("Ownable: caller is not the owner"):
    fund_me.withdraw(sender=bad_actor)
```

```python
# Before
with pytest.raises(exceptions.VirtualMachineError):
    fund_me.withdraw({"from": bad_actor})

# After
from ape.exceptions import ContractLogicError

with pytest.raises(ContractLogicError):
    fund_me.withdraw(sender=bad_actor)
```

Official docs: [Testing](./testing.html)

### Testing: pytest Fixtures

Ape tests use pytest fixtures from the `ape-test` plugin.
In Ape, contract types are not injected as pytest fixtures.
Use the `project` fixture and access contracts as `project.ContractName`.

Remove Brownie's `fn_isolation` fixture when migrating tests:

```python
# Before
@pytest.fixture(autouse=True)
def isolate(fn_isolation):
    pass

# After
# Remove entirely — Ape handles test isolation through its pytest plugin.
```

Use Ape's `accounts` fixture with `project` for deployments:

```python
# Before
def test_deploy(Token, accounts):
    account = accounts[0]
    token = Token.deploy({"from": account})

# After
def test_deploy(project, accounts):
    account = accounts[0]
    token = project.Token.deploy(sender=account)
```

Update contract fixture patterns the same way:

```python
# Before
@pytest.fixture
def token(Token, accounts):
    return Token.deploy({"from": accounts[0]})

# After
@pytest.fixture
def token(project, accounts):
    return project.Token.deploy(sender=accounts[0])
```

If tests manually use chain snapshots, `chain.snapshot()` remains similar, but Brownie's `chain.revert()` should become Ape's `chain.restore()`.

```python
# Before
chain.snapshot()
chain.revert()

# After
chain.snapshot()
chain.restore()
```

Brownie provides a `web3` pytest fixture for direct Web3.py access in tests.
Ape does not provide a `web3` fixture.

If direct Web3 access is needed, use the active provider:

```python
# Before
def test_block_number(web3):
    assert web3.eth.block_number >= 0

# After
from ape import networks

def test_block_number():
    assert networks.provider.web3.eth.block_number >= 0
```

Official docs: [Testing](./testing.html)

### Config Files

Brownie configuration values should move into Ape's `ape-config.yaml` structure. Wallet private keys are not copied into config; import an Ape account alias instead.

```yaml
# Before: brownie-config.yaml
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

```yaml
# After: ape-config.yaml
name: migrated-ape-project
plugins:
  - name: solidity
solidity:
  version: 0.8.20
  import_remapping:
    - "@chainlink=smartcontractkit/chainlink-brownie-contracts@1.1.1"
ethereum:
  default_network: local
# Import keys with `ape accounts import <alias>` and use `accounts.load("<alias>")`.
networks:
  development:
    verify: false
```

Official docs: [Config](./config.html)
