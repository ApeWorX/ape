## Testing Strategy

Due to it's plugin-based architecture and registration as a pytest plugin, testing the mechnanics
of the core Ape repository is a bit more complex than other Python-based repositories.

### MyPy Type Annotations

This codebase uses MyPy extensively, not only to help aide in finding typing issues within the
codebase, but also as a means to help plugin writers avoid integration issues with the library.
Please try to use MyPy Type Annotations as much as possible in the Core codebase, except where
there exists an issue that would hugely complicate it's use from a lack of available machinery.

### Functional Tests

Functional testing covers the unit testing of different functional elements of the Ape library's
API types and plugin-based managers. Each folder underneath this folder represents one functional
component of Ape e.g. `accounts`, `networks`, etc.

Use this section to improve coverage and discovery of lower-level parts of the Ape codebase. This
section should achieve 100% coverage when executed alongside the Integration Test suite by filling
in gaps in the Integration suite's testing.

Code under test should be directly imported from the Ape core library's submodules, and abstract
classes should be subclassed for testing purposes to achieve maximal coverage of their behavior.

### Integration Tests

Integration Testing covers the end-user level testing scenarios that we expect our various classes
of users to encounter in using Ape as both a CLI and plugin system. For testing the plugin writers'
experience, various testing-only plugin modules are defined to validate that the plugin writing
experience stays consistent, as well as ensuring that API objects do not contain breaking changes.

For testing user-level interactions, the use of Click's testing functionality allow us to run the
CLI under various configurations, including over a series of projects that simulate different ways
the application can be used in production.

This section should try to maximize coverage as much as possible, however if a piece of
functionality is much more difficult to test in this way, Functional testing may be used. Running
the Integration test suite by itself may not achieve full coverage, but it should be somewhere
above 80% in practice.

### Fuzzing Tests

Certain tests may be turned into property-based tests via the `hypothesis` fuzzing library, and
should appropiately be marked with the `fuzzing` pytest marker. These tests will run in a separate
CI pass as they might take time to execute. Use fuzz testing under conditions where it is not
possible to parametrize all of the behaviors in a particular code path, especially when the
codebase is complex and has varying behavior. Fuzz testing is particularly useful in finding issues
with code that is very user-configurable, and can often find issues much more cheaply than more
advanced types of analysis-based testing tools.
