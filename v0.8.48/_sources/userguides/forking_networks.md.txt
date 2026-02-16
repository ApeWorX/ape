# Forking Networks

You can fork live networks in Ape to test against real blockchain state locally.
To do so, ensure you are using a provider plugin with forking features.
Some options are:

1. [ApeWorX/ape-foundry](https://github.com/ApeWorX/ape-foundry)
2. [ApeWorX/ape-hardhat](https://github.com/ApeWorX/ape-hardhat)

You can install one of these plugins by doing:

```shell
ape plugins install <foundry|hardhat>
```

## Basic Fork Configuration

Ensure you have also configured your upstream network (the network you are forking).
For example, if forking `ethereum:mainnet` and using `alchemy`, set `alchemy` as the default mainnet provider:

```yaml
ethereum:
  mainnet:
    default_provider: alchemy
```

Now, you can start and connect to your forked-network:

```shell
ape console --network ethereum:mainnet-fork:foundry
```

Learn more about setting up networks in the [the networks guide](./networks.html).

## Advanced Fork Configuration

You can configure additional fork options in your `ape-config.yaml` file:

```yaml
ethereum:
  mainnet_fork:
    default_provider: foundry
    fork:
      # Fork from a specific block number
      block_number: 17000000
      # Optionally enable RPC caching to speed up fork initialization
      cache: true
      # Override default upstream provider if needed
      upstream_provider: alchemy
```

## Forking Plugin Networks

You can also fork L2 plugin networks.
For example, to fork a network such as Optimism or Arbitrum, install the corresponding plugin:

```shell
ape plugins install optimism
ape plugins install arbitrum
```

Then, just like you did for `ethereum`, configure the default mainnet provider:

```yaml
optimism:
  mainnet:
    default_provider: alchemy

arbitrum:
  mainnet:
    default_provider: alchemy
```

Now, you can start and connect to your forked-network:

```shell
ape console --network optimism:mainnet-fork:foundry
ape console --network arbitrum:mainnet-fork:foundry
```

## Configure Default

If you want to change the default network from `local` to your forked network, add the following config:

```yaml
<ecosystem-name>:
  default_network: <network-name>_fork
```

Where `ecosystem-name` is the ecosystem containing the network and `network-name` is the network you are forking.

## Forked Context

If you are already connected to a live network and wish to temporarily fork it, use the [fork() context manager](../methoddocs/managers.html#ape.managers.networks.NetworkManager.fork):

```python
from ape import networks

with networks.ethereum.mainnet.use_provider("alchemy") as alchemy:
    # Connect to live network
    print(f"Connected to: {alchemy.name}")
    
    # Create a fork of the current network using the specified fork provider
    with networks.fork(provider_name="foundry") as fork:
        print(f"Now using fork: {fork.name}")
        
    # You can specify a block number (using the configured default fork provider)
    with networks.fork(provider_name="foundry", block_number=17000000) as fork:
        print(f"Using fork at block {fork.chain.blocks.height}")
```

## Time Travel in Forks

One powerful feature of forking is the ability to manipulate block timestamps for testing time-dependent contracts:

```python
from ape import networks, chain

with networks.ethereum.mainnet.fork() as provider:
    # Advance time by 7 days
    chain.pending_timestamp += 7 * 24 * 60 * 60
    
    # Now you can test time-sensitive contract behavior
    my_contract.check_time_dependent_function()
```

Learn more about the fork context manager [here](./networks.html#forked-context).
