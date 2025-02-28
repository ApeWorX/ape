# Ape Framework - Codebase Analysis

## Overview

Ape Framework is a comprehensive Web3 development tool designed for compiling, testing, and interacting with smart contracts through a unified command line interface. It features a modular plugin system supporting multiple contract languages and blockchain networks.

## Core Architecture

### Manager-Based Design

Ape is built around a system of specialized managers that each handle specific functionality:

- **AccountManager**: Handles wallet and account management
- **ChainManager**: Manages blockchain interactions
- **CompilerManager**: Coordinates contract compilation
- **ConfigManager**: Handles configuration across the framework
- **ConversionManager**: Manages data type conversions
- **NetworkManager**: Manages blockchain network connections
- **PluginManager**: Handles plugin discovery and registration
- **ProjectManager**: Manages project files, dependencies, and contracts
- **QueryManager**: Handles data queries

These managers follow a singleton pattern and are typically accessed through dependency injection.

### Plugin System

The plugin system is built on top of the `pluggy` library with custom extensions:

- **Plugin Types**: Various plugin interfaces (AccountPlugin, CompilerPlugin, NetworkPlugin, etc.)
- **Registration System**: Decorator-based plugin registration using `@plugins.register`
- **Plugin Discovery**: Uses Python's entry points for automatic plugin discovery
- **Plugin Isolation**: Plugins can extend functionality without modifying core code

### CLI Structure

The CLI is built using Click with custom extensions:

- **Command Structure**: Hierarchical command structure
- **Entry Points**: Uses entry_points for plugin CLI integration
- **Dynamic Command Discovery**: Automatically discovers commands from plugins
- **Rich Output**: Uses the rich library for formatted console output

## Core Abstractions

- **Contracts**: Rich abstractions (ContractContainer, ContractInstance) for working with smart contracts
- **Addresses**: Type-safe handling of blockchain addresses
- **Transactions**: Abstractions for creating and sending transactions
- **Networks**: Ecosystem-based network representation

## Build System & Dependencies

- Uses setuptools with setuptools_scm for version management
- Distributed as "eth-ape" Python package via PyPI
- Python 3.9-3.12 supported
- Uses a src-layout with packages in src/ directory

### Core Dependencies

- **Click**: CLI commands (>=8.1.6,\<9)
- **Pydantic**: Data validation (>=2.10.0,\<3)
- **PyYAML**: Configuration (>=5.0,\<7)
- **Web3.py**: Ethereum interaction (>=6.20.1,\<8)
- **Pandas**: Data handling (>=2.2.2,\<3)
- **Pytest**: Testing (>=8.0,\<9.0)
- **IPython**: Console interactions (>=8.18.1,\<9)

## Testing Approach

- **Test Categories**:

  - functional/ - Unit and functional tests
  - integration/ - Integration tests, especially CLI operations
  - performance/ - Performance specific tests

- Uses pytest with custom fixtures in conftest.py

- Test isolation features to avoid affecting user's environment

## Development Practices

### Coding Standards

- Type hints with mypy validation
- 100-character line length
- Uses Pydantic for data models
- Consistent import formatting with isort
- Python 3.9+ features
- Explicit version constraints

### Commit Style

The project follows the Conventional Commits specification:

- **Types**: `feat:`, `fix:`, `refactor:`, `test:`, etc.
- **Scopes**: Optional scope in parentheses, e.g., `refactor(contracts):`
- **Breaking Changes**: Indicated with an exclamation mark, e.g., `feat!:`
- **PR References**: PR numbers included at the end, e.g., `(#2527)`
- **Issue References**: Referenced in square brackets, e.g., `[APE-1374]`
- **Code References**: Surrounded with backticks, e.g., `ContractContainer.at`
- **Commit Messages**: Concise and descriptive, focusing on what changes were made and why

### Common Patterns

- **Dependency Injection**: Managers are accessible through a mixin
- **Lazy Loading**: Extensive use of `__getattr__` for performance
- **Type Safety**: Extensive use of type annotations and validation
- **API Consistency**: Consistent interface design across components
- **Pydantic Models**: Used for data validation and serialization
- **Error Handling**: Custom exception hierarchy
- **Dynamic Attribute Resolution**: Extensive use of dynamic attribute resolution
- **Configuration as Code**: YAML-based configuration with validation

## Contributing

1. Clone the repo
2. Create and activate virtual environment
3. Install dev dependencies: `pip install -e .[dev]`
4. Set up pre-commit hooks: `pre-commit install`
5. Write code with tests
6. Run tests with pytest
7. Submit a pull request

## Development Tooling

- Pre-commit hooks for code quality:

  - black - formatting (line length 100)
  - isort - import sorting
  - flake8 - linting
  - mypy - type checking
  - mdformat - markdown formatting

- Documentation uses sphinx-ape

## Core Plugins

The framework includes several core plugins bundled with the main package:

- ape_accounts: Account management
- ape_compile: Contract compilation
- ape_console: Interactive console
- ape_ethereum: Ethereum ecosystem support
- ape_geth: Go-Ethereum integration
- ape_networks: Network configuration
- ape_node: Node integration
- ape_plugins: Plugin management
- ape_pm: Package management
- ape_test: Testing framework
