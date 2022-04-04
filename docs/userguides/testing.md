### Testing

Testing an ape project is important and easy.
All tests must be stored under `tests/`. Each test must start with `test_` and end with the `.py` extension.

```bash
ape test
```

To run a particular test:

```bash
ape test test_my_contract
```

Additionally, you can use `-I` to open interactive mode and `-s` to print logs.

```bash
ape test test_my_contract -I -s
```