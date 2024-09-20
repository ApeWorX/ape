# Dependencies

Ape downloads and caches dependencies in the `.ape/packages` folder.
There are three sub-folders in `.ape/packages` for dependencies:

1. `projects/` - contains the raw project files for each dependency in subsequent `/<name>/<version-id>` directories (where `<name>` refers to the path-ified full-name of the dependency, e.g. `"OpenZeppelin_openzeppelin-contracts"`, and `<version-id>` refers to the version or branch of the package).
   This location is where local project compilation looks for additional sources from import statements.
2. `manifests/` - much like your local projects' `.build/__local__.json`, this is where dependencies cache their manifests.
   When you compile a dependency, the contract types are stored in the dependency manifest's JSON file.
3. `api/` - for caching the API data placed in `dependencies:` config or `ape pm install` commands, allowing dependency usage and management from anywhere in the file system.

```{note}
You can install dependencies that don't compile out-of-the-box.
Sometimes, dependencies are only collections of source files not meant to compile on their own but instead be used in projects via import statements.
You can change the settings of a dependency using `config_override:` to compile dependencies after installed, if needed, and the `api/` cache always refers to the latest used during installation or compilation.
```

## Types of Dependencies

There are few dependency types that come with Ape.
The following section highlights how to use each of them and what their differences are.

### GitHub

You can use dependencies from GitHub.
For example, a common dependency for Solidity projects is [Open Zeppelin](https://github.com/OpenZeppelin/openzeppelin-contracts).
To use Open Zeppelin version 4.4.2 in your Ape Solidity project, add the following to your `ape-config.yaml` file:

```yaml
dependencies:
  - name: OpenZeppelin
    github: OpenZeppelin/openzeppelin-contracts
    version: 4.4.2
```

Then, follow the guide below about `remappings` to use the dependency.

```{warning}
**An important WARNING about the `version:` key for GitHub dependencies:**
The `version:` config first attempts to use an official GitHub release, but if the release is not found, it will check the release tags.
```

If you know the version is not available as an official release, bypass the original check by using the `ref:` key.
The `ref:` key is also used for installing branches.

For example, to install a version available as a `git` tag, do the following:

```yaml
dependencies:
  - name: Uniswap
    github: Uniswap/v3-core
    ref: v1.0.0
```

The `ref:` config installs the code from that reference; the `version:` config uses the official GitHub release API, and then only if that fails will it check the `git` references.
Often times, the `v` prefix is required when using tags.
However, if cloning the tag fails, `ape` will retry with a `v` prefix.
Bypass the original failing attempt by including a `v` in your dependency config.

**By knowing if the release is from the version API or only available via tag, and whether the version is v-prefixed or not, you save Ape some time and complexity when installing dependencies.**

### PyPI

You can use dependencies from [PyPI](https://pypi.org/) by using the `pypi:` key.

```yaml
dependencies:
   - pypi: snekmate
     config_override:
       base_path: src
       contracts_folder: snekmate
```

When using the `pypi:` key, dependencies are downloaded and extracted from PyPI using an HTTP requests library.

You can also specify the `python:` key for already-installed dependencies:

```yaml
dependencies:
   - python: snekmate
     config_override:
       contracts_folder: .
```

Using `python:` requires the package to be installed in your `sys.path` (site-packages) folder, generally via `pip` or some other tool.
The `contracts_folder` override, in this case, is often needed because the site-package does not have the root source-folder included.
Additionally, `python:` specified dependencies may also be lacking project-configuration files, such as the `ape-config.yaml`.
Compilers such as `vyper` encourage users to use `pip` to publish and install smart-contract dependencies (other vyper files), but some features in Ape may be limited if the dependency is not also specified in your config somewhere.

If wanting to use a dependency from `PyPI`, we recommend using the `pypi:` key instead of the `python:` key.
However, the `python:` key works great if you already used `pip` to install the dependency, especially if the dependency is not available on `PyPI`.

### Local

You can use already-downloaded projects as dependencies by referencing them as local dependencies.

```yaml
dependencies:
  - name: MyDependency
    local: local/path/to/MyDependency
```

This is helpful when:

- Working on multiple packages at once.
- When there is not a suitable `DependencyAPI` implementation available for downloading your dependency.
- Testing the framework.

You can also reference local project manifests and use those as dependencies.
To do this, use a local value pointing to the manifest file, like this:

```yaml
dependencies:
  - name: MyDependency
    local: ./my-dependency.json
    version: 1.0.0
```

### NPM

You can use dependencies from NPM.
This is generally not recommended.
However, sometimes it is the only way to use a dependency.

To use a dependency from NPM, you must have already run `npm install` and that package must be present in your local `node_modules` folder.
Then, add the following to your config so that Ape can find the dependency:

```yaml
dependencies:
  - name: MyDependency
    npm: "@myorg/mydependency"
    version: v1.3.0
```

## Package Management CLI

You can also install and / or compile dependencies using the `pm` CLI.

### list

To list information about installed dependencies, run:

```shell
ape pm list
```

You should see information like:

```shell
NAME                                 VERSION  INSTALLED  COMPILED
OpenZeppelin/openzeppelin-contracts  4.9.3    True       False
```

### install

To install all dependencies in your project, run:

```shell
ape pm install
```

If the dependencies are already cached and you want to re-install them, use the `--force` flag:

```shell
ape pm install --force
```

To install a dependency that is not in your config, you can specify it directly along with `--name` and `--version`:

```shell
ape pm install gh:OpenZeppelin/openzeppelin-contracts --name openzeppelin --version "4.6.0"
```

```{note}
The `gh:` prefix is used because this dependency is from GitHub.
For `npm` dependencies, you use an `npm:` prefix.
For local dependencies, you give it a path to the local dependency.
`--version` is not required when using a local dependency.
```

To change the config of a dependency when installing, use the `--config-override` CLI option:

```shell
ape pm install gh:OpenZeppelin/openzeppelin-contracts \
  --name openzeppelin \
  --version "4.6.0" \
  --config-override '{"solidity": {"version": "0.8.12"}}'
```

You can also use Python to install dependencies, using `**kwargs` as the same fields you put in your `dependencies:` config:

```python
from ape import project

project.dependencies.install(
   github="OpenZeppelin/openzeppelin-contracts", name="openzeppelin", version="4.4.2"
)
```

### uninstall

Remove previously installed packages using the `uninstall` command, providing it either the dependency's name or package_id:

```shell
ape pm uninstall OpenZeppelin
```

```shell
ape pm uninstall OpenZeppelin/openzeppelin-contracts
```

If there is a single version installed, the command will remove the single version.
If multiple versions are installed, pass additional arguments specifying the version(s) to be removed:

```shell
ape pm uninstall OpenZeppelin 4.5.0 4.6.0
```

To skip the confirmation prompts, use the `--yes` flag (abbreviated as `-y`):

```shell
ape pm uninstall OpenZeppelin all --yes
```

```{note}
Additionally, use the `all` special version key to delete all versions.
```

### compile

Dependencies are not compiled when they are installed.
Dependencies are only compiled if you need them to be.
This is because often times a dependency will not compile in Ape on its own but its contract types can still be used in your project.
However, when working with dependency contracts directly, they will need to be compiled.
Ape compiles them as soon as you request the contracts from them, so it generally happens on the backend automatically.
**However**, you may want to recompile the dependencies, like when using a new compiler version or settings.
You can use the CLI to recompile.

```shell
ape pm compile OpenZeppelin --version 4.6.0 --force
```

```{note}
You only need to specify a version if you have more than one version of a dependency installed.
Otherwise, you just give it the name.
```

To compile all dependencies in your local project, run the command with no arguments while in your project:

```shell
ape pm compile
```

Alternatively, you can compile dependencies along with your project's contracts by using the `--include-dependencies` flag in `ape-compile`:

```shell
ape compile --include-dependencies
```

## Misc

The following guidelines are applicable to **ALL** dependency types.

### Config Override

To use any extra config item for a dependency, such as configurations for compilers needed during compiling, use the `config_override` setting:

```yaml
dependencies:
  - name: dependency
    github: org-name/dependency-project-name
    config_override:
       solidity:
         evm_version: paris
```

This is the same as if these values were in an `ape-config.yaml` file in the project directly.

You can also specify `--config-override` in the `ape pm install` command to try different settings more adhoc:

```shell
ape pm install --config-override '{"solidity": {"evm_version": "paris"}}'
```

### Custom Contracts Folder

You can set the name of the dependency's contracts folder using the `config_override` key, e.g.:

```yaml
dependencies:
  - name: DappToolsERC20
    github: dapphub/erc20
    ref: dappnix
    config_override:
      contracts_folder: src
```

### File Exclusions

To ignore files from a dependency project, use the `exclude` setting in the `config_override:compile` section to specify glob patterns:

```yaml
dependencies:
  - name: dependency-project-name
    github: org-name/dependency-project-name
    config_override:
      compile:
        exclude:
          - package.json    # Ignore package.json files.
          - mocks/**/*      # Ignore all files in the 'mocks' directory
```

### Solidity Import Remapping

A common use-case for dependencies involves the Solidity plugin.
By default, the `ape-solidity` plugin knows to look at installed dependencies for potential remapping-values and will use those when it notices you are importing them.
For example, if you are using dependencies like:

```yaml
dependencies:
  - name: OpenZeppelin
    github: OpenZeppelin/openzeppelin-contracts
    version: 4.4.2
```

And your source files import from `openzeppelin` this way:

```solidity
import "@openzeppelin/contracts/token/ERC721/ERC721.sol";
```

Ape knows how to resolve the `@openzeppelin` value and find the correct source.

If you want to override this behavior or add new remappings that are not dependencies, you can add them to your `ape-config.yaml` under the `solidity:` key.
For example, let's say you have downloaded `openzeppelin` somewhere and do not have it installed in Ape.
You can map to your local install of `openzeppelin` this way:

```yaml
solidity:
  import_remapping:
    - "@openzeppelin=path/to/openzeppelin"
```

### Compiling Dependencies

Sometimes, you may need to access types (such as contract types) from dependencies.
You can achieve this using the project manager:

```python
from ape import accounts, project

# NOTE: This will compile the dependency
dependency_project = project.dependencies["my_dependency"]["1.0.0"]
dependency_contract = dependency_project.DependencyContractType 
my_account = accounts.load("alias")
deployed_contract = my_account.deploy(dependency_contract, "argument")
print(deployed_contract.address)
```

If you would like to always compile dependencies during `ape compile` rather than only have them get compiled upon asking for contract types, you can use the config option `include_dependencies` from the `compile` config:

```yaml
compile:
  include_dependencies: true
```

Alternatively, use the `--include-dependencies` CLI flag:

```shell
ape compile --include-dependencies
```
