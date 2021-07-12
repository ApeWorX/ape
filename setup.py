#!/usr/bin/env python
# -*- coding: utf-8 -*-
from setuptools import find_packages, setup  # type: ignore

extras_require = {
    "test": [  # `test` GitHub Action jobs uses this
        "pytest>=6.0,<7.0",  # Core testing package
        "pytest-xdist",  # multi-process runner
        "pytest-cov",  # Coverage analyzer plugin
        "hypothesis>=6.2.0,<7.0",  # Strategy-based fuzzer
        "hypothesis-jsonschema==0.19.0",  # JSON Schema fuzzer extension
    ],
    "lint": [
        "black>=20.8b1,<21.0",  # auto-formatter and linter
        "mypy>=0.800,<0.900",  # Static type analyzer
        "flake8>=3.8.3,<4.0",  # Style linter
        "isort>=5.7.0,<6.0",  # Import sorting linter
    ],
    "doc": [
        "Sphinx>=3.4.3,<4",  # Documentation generator
        "sphinx_rtd_theme>=0.1.9,<1",  # Readthedocs.org theme
        "towncrier>=19.2.0, <20",  # Generate release notes
    ],
    "release": [  # `release` GitHub Action job uses this
        "setuptools",  # Installation tool
        "wheel",  # Packaging tool
        "twine",  # Package upload tool
    ],
    "dev": [
        "commitizen",  # Manage commits and publishing releases
        "pre-commit",  # Ensure that linters are run prior to committing
        "pytest-watch",  # `ptw` test watcher/runner
        "ipdb",  # Debugger (Must use `export PYTHONBREAKPOINT=ipdb.set_trace`)
    ],
}

# NOTE: `pip install -e .[dev]` to install package
extras_require["dev"] = (
    extras_require["test"]
    + extras_require["lint"]
    + extras_require["doc"]
    + extras_require["release"]
    + extras_require["dev"]
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
        "click>=8.0.0",
        "dataclassy>=0.10.3,<1.0",
        "eth-account>=0.5.2,<0.6.0",
        "pluggy>=0.13.1,<1.0",
        "PyGithub>=1.54,<2.0",
        "pyyaml>=0.2.5",
        "importlib-metadata",
        "singledispatchmethod ; python_version<'3.8'",
        "IPython==7.16",  # Pinned for py3.6
        "jedi==0.17.2",  # Pinned for IPython 7.16 incompatibility
        "web3[tester]>=5.18.0,<6.0.0",
    ],
    entry_points={
        "console_scripts": ["ape=ape._cli:cli"],
        "ape_cli_subcommands": [
            "ape_accounts=ape_accounts._cli:cli",
            "ape_compile=ape_compile._cli:cli",
            "ape_console=ape_console._cli:cli",
            "ape_plugins=ape_plugins._cli:cli",
            "ape_run=ape_run._cli:cli",
            "ape_networks=ape_networks._cli:cli",
        ],
    },
    python_requires=">=3.6,<3.10",
    extras_require=extras_require,
    py_modules=[
        "ape",
        "ape_accounts",
        "ape_compile",
        "ape_console",
        "ape_ethereum",
        "ape_etherscan",
        "ape_infura",
        "ape_networks",
        "ape_plugins",
        "ape_run",
        "ape_test",
        "ape_pm",
    ],
    license="Apache-2.0",
    zip_safe=False,
    keywords="ethereum",
    packages=find_packages("src"),
    package_dir={"": "src"},
    package_data={
        "ape": ["py.typed"],
        "ape_accounts": ["py.typed"],
        "ape_compile": ["py.typed"],
        "ape_ethereum": ["py.typed"],
        "ape_etherscan": ["py.typed"],
        "ape_infura": ["py.typed"],
        "ape_run": ["py.typed"],
        "ape_test": ["py.typed"],
        "ape_pm": ["py.typed"],
    },
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: MIT License",
        "Natural Language :: English",
        "Operating System :: MacOS",
        "Operating System :: POSIX",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.6",
        "Programming Language :: Python :: 3.7",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
    ],
)
