# the Ape Pytest Plugin

The `ape_test` core plugin is responsible for invoking tests.
However, to correctly integrate with `pytest`, the `ape_test` plugin needs to register itself as a pytest plugin.
Registering `ape_test` as a `pytest` plugin within the `ape_test` plugin causes race conditions in the global plugin registration context.
Specifically, parts of the `ape_test` plugin to fail to register in time after invoking `pytest`, such as the providers and the accounts.
By handling the pytest plugin registration here, we avoid these issues.
