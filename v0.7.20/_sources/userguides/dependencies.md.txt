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

To list information about the dependencies in your local project, run:

```shell
ape pm list
```

To list information about all installed dependencies across all projects, run:

```shell
ape pm list --all
```

You should see information like:

```shell
Packages:
  OpenZeppelin v4.6.0, compiled!
  vault master
  vault v0.4.5
  gnosis v1.3.0
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

**NOTE**: The `gh:` prefix is used because this dependency is from GitHub.
For `npm` dependencies, you use an `npm:` prefix.
For local dependencies, you give it a path to the local dependency.
`--version` is not required when using a local dependency.

To change the config of a dependency when installing, use the `--config-override` CLI option:

```shell
ape pm install gh:OpenZeppelin/openzeppelin-contracts \
  --name openzeppelin \
  --version "4.6.0" \
  --config-override '{"solidity": {"version": "0.8.12"}}'
```

### remove

Remove previously installed packages using the `remove` command:

```shell
ape pm remove OpenZeppelin
```

If there is a single version installed, the command will remove the single version.
If multiple versions are installed, pass additional arguments specifying the version(s) to be removed:

```shell
ape pm remove OpenZeppelin 4.5.0 4.6.0
```

To skip the confirmation prompts, use the `--yes` flag (abbreviated as `-y`):

```shell
ape pm remove OpenZeppelin all --yes
```

**NOTE**: Additionally, use the `all` special version key to delete all versions.

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

**NOTE**: You only need to specify a version if you have more than one version of a dependency installed.
Otherwise, you just give it the name.

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

### Compiling Dependencies

Sometimes, you may need to access types (such as contract types) from dependencies.
You can achieve this using the project manager:

```python
from ape import accounts, project

# NOTE: This will compile the dependency
dependency_contract = project.dependencies["my_dependency"]["1.0.0"].DependencyContractType
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
