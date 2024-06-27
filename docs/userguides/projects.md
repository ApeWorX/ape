# Developing Projects with Ape

Use `ape init` to create your project.
A common project structure looks like this:

```
project                             # The root project directory
├── contracts/                      # Project source files, such as '.sol' or '.vy' files
│   └── smart_contract_example.sol  # Sample of a smart contract
├── tests/                          # Project tests, ran using the 'ape test' command
│   └── test_sample.py              # Sample of a test to run against your sample contract
├── scripts/                        # Project scripts, such as deploy scripts, ran using the 'ape run   <`name>' command
│   └── deploy.py                   # Sample script to automate a deployment of an ape project
└── ape-config.yaml                 # The ape project configuration file
```

Notice that you can configure you ape project using the `ape-config.yaml` file.
See the [configuration guide](./config.html) for a more detailed explanation of settings you can adjust.

## The Local Project

After you have a local project and you are in the directory of that project, the global `project` reference in Ape will refer to this project.
You can see this by typing `project` in the `ape console`:

```python
In [1]: project
Out[1]: <ProjectManager ~/ApeProjects/ape-demo-project>
```

In this case, my terminal's current working directory is the same as a local project named `ape-demo-project`.

## Other Projects

You can reference other local projects on your computer by using the `Project` factory class (notice the capital `P`):

```python
from ape import Project

my_other_project = Project("../path/to/my/other/project")
_ = my_other_project.MyContract  # Do anything you can do to the root-level project.
```

## Project Manifests

Ape stores and caches artifacts in an [EthPM package manifest](https://eips.ethereum.org/EIPS/eip-2678).
When working with local projects, the manifests get placed in the `<project-path>/.build/__local__.json`.
However, you may obtain a manifest from a different location.
If that is the case, you can create a project directly from the manifest itself:

```python
from ape import Project

# Pass in a manifest (object or dictionary), or a path to a manifest's JSON file.
project = Project.from_manifest("path/to/manifest.json")
_ = project.MyContract  # Do anything you can do to the root-level project.
```

## Installed Python Projects

If you have installed a project using `pip` or alike and you wish to reference its project, use the `Project.from_python_library()` class method.

```python
from ape import Project

snekmate = Project.from_python_library("snekmate", config_override={"contracts_folder": "."})
```

## Dependencies

Use other projects as dependencies in Ape.
There is an extensive guide you can read on this [here](./dependencies.html).
But it is important to note that the dependency system largely is dependent on the project system.
Dependencies are just projects after all; projects containing source files you both use in your projects or compile independently.

For example, access a dependency project and treat it like any other project this way:

```python
from ape import project

dependency = project.dependencies.get_dependency("my-dependency", "1.0.0")
contract_type = dependency.project.ContractFromDependency
```
