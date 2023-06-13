# Dependencies

Ape downloads and caches dependencies in the `.ape/packages/<name>/<version-id>` directory where `<name>` refers to the name of the dependency and `<version-id>` refers to the version or branch of the package.
When first downloading dependencies, Ape only places the source contents in the `sources` field of the `PackageManifest` and leaves the `contract_types` field untouched.
This is because dependencies may not compile by Ape's standard out-of-the-box but their contract types can still be used in projects that do.

To use dependencies in your projects, you must configure them in your `ape-config.yaml` file.

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

**An important WARNING about the `version:` key for GitHub dependencies:**
The `version:` config first attempts to use an official GitHub release, but if the release is not found, it will check the release tags.
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

### Local

You can use already-downloaded projects as dependencies by referencing them as local dependencies.

```yaml
dependencies:
  - name: MyDependency
    local: local/path/to/MyDependency
    contracts_folder: src/contracts
```

This is helpful when:

- Working on multiple packages at once.
- When there is not a suitable `DependencyAPI` implementation available for downloading your dependency.
- Testing the framework.

### NPM

You can use dependencies from NPM.
This is generally not recommended.
However, sometimes it is the only way to use a dependency.

To use a dependency from NPM, you must have already run `npm install` and that package must be present in your local `node_modules` folder.
Then, add the following to your config so that Ape can find the dependency:

```yaml
dependencies:
  - name: MyDependency
    npm: @myorg/mydependency
    version: v1.3.0
```

## Misc

The following guidelines are applicable to **ALL** dependency types.

### Custom Contracts Folder

You can set the name of the dependency's contracts folder, e.g.:

```yaml
dependencies:
  - name: DappToolsERC20
    github: dapphub/erc20
    ref: dappnix
    contracts_folder: src
```

### File Exclusions

To ignore files from a dependency project, use the `exclude` setting to specify glob patterns:

```yaml
dependencies:
  - name: dependency-project-name
    github: org-name/dependency-project-name
    exclude:
      - package.json    # Ignore package.json files.
      - mocks/**/*      # Ignore all files in the 'mocks' directory
```

### Solidity Remappings

A common use-case for dependencies involves the Solidity plugin.
To use your dependencies in the `ape-solidity` plugin, configure `import_remappings` to refer to them:

```yaml
dependencies:
  - name: OpenZeppelin
    github: OpenZeppelin/openzeppelin-contracts
    version: 4.4.2

solidity: 
  import_remapping:
    - "@openzeppelin=OpenZeppelin/4.4.2"
```

Now, in your solidity files, import `OpenZeppelin` sources via:

```solidity
import "@openzeppelin/token/ERC721/ERC721.sol";
```

### Accessing Dependency Types

Sometimes, you may need to access types (such as contract types) from dependencies.
You can achieve this using the project manager:

```python
from ape import accounts, project

dependency_contract = project.dependencies["my_dependency"]["1.0.0"].DependencyContractType
my_account = accounts.load("alias")
deployed_contract = my_account.deploy(dependency_contract, "argument")
print(deployed_contract.address)
```
