#!/usr/bin/env python
from pathlib import Path
from typing import Dict

from setuptools import find_packages, setup  # type: ignore

here = Path(__file__).parent.absolute()
packages_data: Dict = {}
with open(here / "src" / "ape" / "__modules__.py", encoding="utf8") as modules_file:
    exec(modules_file.read(), packages_data)

extras_require = {
    "test": [  # `test` GitHub Action jobs uses this
        "pytest-xdist",  # multi-process runner
        "pytest-cov",  # Coverage analyzer plugin
        "pytest-mock",  # For creating mocks
        "hypothesis>=6.2.0,<7.0",  # Strategy-based fuzzer
        "hypothesis-jsonschema==0.19.0",  # JSON Schema fuzzer extension
    ],
    "lint": [
        "black>=22.10.0,<23",  # auto-formatter and linter
        "mypy>=0.982,<1",  # Static type analyzer
        "types-PyYAML",  # NOTE: Needed due to mypy typeshed
        "types-requests",  # NOTE: Needed due to mypy typeshed
        "types-pkg-resources",  # NOTE: Needed due to mypy typeshed
        "pandas-stubs==1.2.0.62",  # NOTE: Needed due to mypy typeshed
        "types-SQLAlchemy>=1.4.49",
        "flake8>=5.0.4,<6",  # Style linter
        "flake8-breakpoint>=1.1.0,<2",  # detect breakpoints left in code
        "flake8-print>=4.0.0,<5",  # detect print statements left in code
        "isort>=5.10.1,<6",  # Import sorting linter
        "pandas-stubs==1.2.0.62",  # NOTE: Needed due to mypy types
    ],
    "doc": [
        "myst-parser>=0.17.0,<0.18",  # Tools for parsing markdown files in the docs
        "sphinx-click>=3.1.0,<4.0",  # For documenting CLI
        "Sphinx>=4.4.0,<5.0",  # Documentation generator
        "sphinx_rtd_theme>=1.0.0,<2",  # Readthedocs.org theme
        "sphinxcontrib-napoleon>=0.7",  # Allow Google-style documentation
    ],
    "release": [  # `release` GitHub Action job uses this
        "setuptools",  # Installation tool
        "wheel",  # Packaging tool
        "twine==3.8.0",  # Package upload tool
    ],
    "dev": [
        "commitizen>=2.19,<2.20",  # Manage commits and publishing releases
        "pre-commit",  # Ensure that linters are run prior to committing
        "pytest-watch",  # `ptw` test watcher/runner
        "ipdb",  # Debugger (Must use `export PYTHONBREAKPOINT=ipdb.set_trace`)
    ],
    # NOTE: These are extras that someone can install to get up and running quickly w/ ape
    #       They should be kept up to date with what works and what doesn't out of the box
    #       Usage example: `pipx install eth-ape[recommended-plugins]`
    "recommended-plugins": (here / "recommended-plugins.txt").read_text().split("\n"),
}

# NOTE: `pip install -e .[dev]` to install package
extras_require["dev"] = (
    extras_require["test"]
    + extras_require["lint"]
    + extras_require["doc"]
    + extras_require["release"]
    + extras_require["dev"]
    # NOTE: Do *not* install `recommended-plugins` w/ dev
)

with open("./README.md") as readme:
    long_description = readme.read()


setup(
    name="eth-ape",
    use_scm_version=True,
    setup_requires=["setuptools_scm"],
    description="Ape Ethereum Framework",
    long_description=long_description,
    long_description_content_type="text/markdown",
    author="ApeWorX Ltd.",
    author_email="admin@apeworx.io",
    url="https://github.com/ApeWorX/ape",
    include_package_data=True,
    install_requires=[
        "backports.cached_property ; python_version<'3.8'",
        "click>=8.1.3,<9",
        "ijson>=3.1.4,<4",
        "importlib-metadata",
        "ipython>=8.5.0,<9",
        "packaging>=20.9,<21",
        "pandas>=1.3.0,<2",
        "pluggy>=1.0.0,<2",
        "pydantic>=1.9.2,<2",
        "pygit2>=1.7.2,<2",
        "PyGithub>=1.54,<2",
        "pytest>=6.0,<8.0",
        "python-dateutil>=2.8.2,<3",
        "pyyaml>=6.0,<7",
        "requests>=2.28.1,<3",
        "rich>=12.5.1,<13",
        "SQLAlchemy>=1.4.35",
        "tqdm>=4.62.3,<5.0",
        "traitlets>=5.3.0",
        "watchdog>=2.1.9,<3.0",
        # ** Dependencies maintained by Ethereum Foundation **
        "eth-abi>=3.0.1,<4",
        "eth-account>=0.7,<0.8",
        "eth-typing>=3.1,<4",
        "eth-utils>=2.0.0,<3",
        "hexbytes>=0.2.3,<1",
        "py-geth>=3.8.0,<4",
        "web3[tester]==6.0.0b6",
        # ** Dependencies maintained by ApeWorX **
        "eip712>=0.1.4,<0.2",
        "ethpm-types>=0.3.7,<0.4",
        "evm-trace>=0.1.0a10",
    ],
    entry_points={
        "console_scripts": ["ape=ape._cli:cli"],
        "pytest11": ["ape_test=ape.pytest.plugin"],
        "ape_cli_subcommands": [
            "ape_accounts=ape_accounts._cli:cli",
            "ape_cache=ape_cache._cli:cli",
            "ape_compile=ape_compile._cli:cli",
            "ape_console=ape_console._cli:cli",
            "ape_plugins=ape_plugins._cli:cli",
            "ape_run=ape_run._cli:cli",
            "ape_networks=ape_networks._cli:cli",
            "ape_test=ape_test._cli:cli",
            "ape_init=ape_init._cli:cli",
        ],
    },
    python_requires=">=3.8,<3.11",
    extras_require=extras_require,
    py_modules=packages_data["__modules__"],
    license="Apache-2.0",
    zip_safe=False,
    keywords="ethereum",
    packages=find_packages("src"),
    package_dir={"": "src"},
    package_data={p: ["py.typed"] for p in packages_data["__modules__"]},
    classifiers=[
        "Development Status :: 5 - Production/Stable",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: MIT License",
        "Natural Language :: English",
        "Operating System :: MacOS",
        "Operating System :: POSIX",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
    ],
)
