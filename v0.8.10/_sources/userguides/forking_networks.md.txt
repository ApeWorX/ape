# Forking Networks

You can fork live networks in Ape.
To do so, ensure you are using a provider plugin with forking features.
Some options are:

1. [ApeWorX/ape-foundry](https://github.com/ApeWorX/ape-foundry)
2. [ApeWorX/ape-hardhat](https://github.com/ApeWorX/ape-hardhat)

You can install one of these plugins by doing:

```shell
ape plugins install <foundry|hardhat>
```

Ensure you have also configured your upstream network (the network you are forking).
For example, if forking `ethereum:mainnet` and using `alchemy`, set `alchemy` as the default mainnet provider:

```yaml
ethereum:
  mainnet:
    default_provider: alchemy
```

Now, you can start and connect to your forked-network:

```yaml
ape console --network ethereum:mainnet-fork:foundry
```

Learn more about setting up networks in the [the networks guide](./networks.html).

## Forking Plugin Networks

You can also fork L2 plugin networks.
For example, to fork a network such as Optimism, install the `ape-optimism` plugin:

```shell
ape plugins install optimism
```

Then, just like you did for `ethereum`, configure `optimism`'s default mainnet provider:

```yaml
optimism:
  mainnet:
    default_provider: alchemy
```

Now, you can start and connect to your forked-network:

```yaml
ape console --network optimism:mainnet-fork:foundry
```

## Configure Default

If you want to change the default network from `local` to your forked network, add the following config:

```yaml
<ecosystem-name>:
  default_network: <network-name>_fork
```

Where `ecosystem-name` is the ecosystem containing the network and `network-name` is the network you are forking.

## Forked Context

If you are already connected to a live network wish to temporarily fork it, use the [fork() context manager](../methoddocs/managers.html#ape.managers.networks.NetworkManager.fork):

```python
from ape import networks

def main():
    with networks.ethereum.mainnet.use_provider("alchemy") as alchemy:
        print(alchemy.name)
        with networks.fork(provider_name="foundry") as foundry:
            print(foundry.name)
```

Learn more about the fork context manager [here](./networks.html#forked-context).
