# ape

```{eval-rst}
.. attribute:: ape.accounts

   Manage accounts.
   See the `AccountManager <../methoddocs/managers.html#ape.managers.accounts.AccountManager>`__ for more info.
```

```{eval-rst}
.. attribute:: ape.chain

   Manage the blockchain.
   See the `ChainManager <../methoddocs/managers.html#ape.managers.chain.ChainManager>`__ for more info.
```

```{eval-rst}
.. attribute:: ape.networks

   Manage networks.
   See the `NetworkManager <../methoddocs/managers.html#ape.managers.networks.NetworkManager>`__ for more info.
```

```{eval-rst}
.. attribute:: ape.project

   Access the local project.
   See the `ProjectManager <../methoddocs/managers.html#ape.managers.project.ProjectManager>`__ for more info.
```

```{eval-rst}
.. attribute:: ape.config

   Access the local project config.
   See the `ConfigManager <../methoddocs/managers.html#ape.managers.config.ConfigManager>`__ for more info.
```

```{eval-rst}
.. function:: ape.Project(path)

   Instantiate other projects.
   See the `ProjectManager <../methoddocs/managers.html#ape.managers.project.ProjectManager>`__ for more info.
   
   :path: The path to the project.
```

```{eval-rst}
.. function:: ape.Contract(address, contract_type)

   Instantiate contract-classes at a given address.
   See the `ContractInstance <../methoddocs/contracts.html#ape.contracts.base.ContractInstance>`__ for more info.
   
   :address: The address of the instance.
   :contract_type: Optionally provide the ABI or contract type data.
```

```{eval-rst}
.. function:: ape.convert(value, to_type)

   Conversion utility.
   See the `ConversionManager <../methoddocs/managers.html#ape.managers.converters.ConversionManager>`__ for more info.
   
   :value: The value to convert.
   :to_type: The destination type.
   
   Example usage::

      result = ape.convert("1 ETH", int)
```

```{eval-rst}
.. attribute:: ape.compilers

   Access compiler classes.
   See the `CompilerManager <../methoddocs/managers.html#ape.managers.compilers.CompilerManager>`__ for more info.
```

```{eval-rst}
.. function:: ape.reverts(expected_message, dev_message)

   Catch contract-revert exceptions.
   Mimics ``pytest.raises``.
   
   :expected_message: The expected revert message (optional).
   :dev_message: The expected dev-message (optional).
```
