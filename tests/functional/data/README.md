# Test Data

All contracts use `.JSON` contract types because core tests cannot assume `ape-vyper` or `ape-solidity` is installed.
These artifacts are stored in `tests/functional/data/contracts/ethereum/local`.
Their counter-part actual source files are located in `tests/functional/data/sources` and have corresponding names (e.g. `SolidityContract.json` matches up with `SolidityContract.sol`).

## Making Changes

To make changes to the source files, first ensure you have `ape-solidity` and/or `ape-vyper` installed and then edit the files in `sources/`.
After you are ready to test your changes, from this directory, run the following script:

```shell
ape run update <MyContract>
```

Now, it's corresponding JSON file should have been updated.
