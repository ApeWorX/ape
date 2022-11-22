# Accounts

Accounts in Ape come from [AccountAPI](../methoddocs/api.html#ape.api.accounts.AccountAPI) implementations (e.g. from plugins).
There are typically two types of accounts:

1. Test accounts
2. Live network accounts

Test accounts are useful for local network testing and debugging contracts.
Live network accounts are for interacting with live blockchains and should be secured.

To learn more about Ethereum accounts, see [the Ethereum documentation](https://ethereum.org/en/developers/docs/accounts/).

## Test Accounts

Ape ships with pytest fixtures to assist in writing your tests.
Pre-funded test accounts are accessible via the [accounts fixture](./testing.html#accounts-fixture).

```python
def test_my_contract_method(accounts):
    sender = accounts[0]
    ...
```

To access the same prefunded accounts in your scripts or console, use the root `accounts` object and the [test_accounts](../methoddocs/managers.html#ape.managers.accounts.AccountManager.test_accounts) property:

```python
from ape import accounts

sender = accounts.test_accounts[0]
```

You can configure your test accounts using your `ape-config.yaml` file:

```yaml
test:
  mnemonic: test test test test test test test test test test test junk
  number_of_accounts: 5
```

**WARN**: NEVER put a seed phrase with real funds here.
The accounts generated from this seed are solely for testing and debugging purposes.

Learn more about test accounts from the [testing guide](./testing.html#accounts-fixture).

## Live Network Accounts

When using live networks, you need to get your accounts into Ape.
Ape ships with a keyfile accounts plugin to assist with this.
All the available CLI commands for this accounts plugin can be found [here](../commands/accounts.html).

For example, you can [generate](../commands/accounts.html#accounts-generate) an account:

```bash
ape accounts generate <ALIAS>
```

It will prompt you for a passphrase.

If you already have an account and you wish to import it into Ape (say, from Metamask), you can use the [import command](../commands/accounts.html#accounts-import):

```bash
ape accounts import <ALIAS>
```

It will prompt you for the private key.
If you need help exporting your private key from Metamask, see [this guide](https://metamask.zendesk.com/hc/en-us/articles/360015289632-How-to-export-an-account-s-private-key).

Then, in your scripts, you can [load](../methoddocs/managers.html#ape.managers.accounts.AccountManager.load) an account:

```python
from ape import accounts

account = accounts.load("<ALIAS>")
```

## Automation

If you use your keyfile accounts in automation, such as CI/CD, you may need to programmatically unlock them and enable autosign.
**WARNING**: We don't recommend using this approach but it is possible due to sometimes being needed.
Ensure you are using a secure environment and are aware of what you are doing.

```python
from ape import accounts
from eth_account.messages import encode_defunct

account = accounts.load("<ALIAS>")
account.set_autosign(True, passphrase="<PASSPHRASE>")

# Now, you will not be prompted to sign messages or transactions
message = encode_defunct(text="Hello Apes!")
signature = account.sign_message(message)
```

## Hardware Wallets

Because of the plugin system in Ape, we are able to support other types of accounts including hardware wallet accounts.
Check out these plugins:

* [ape-ledger](https://github.com/ApeWorX/ape-ledger)
* [ape-trezor](https://github.com/ApeWorX/ape-trezor)

To install one of these plugins, do the following:

```bash
ape plugins install ledger
```
