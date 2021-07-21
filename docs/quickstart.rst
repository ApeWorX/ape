Quickstart guide
################

Installation
************

via ``pip``
===========

You can install the latest release via `pip <https://pypi.org/project/pip/>`_:

.. code-block:: bash

    pip install eth-ape

via ``setuptools``
==================

You can clone the repository and use `setuptools <https://github.com/pypa/setuptools>`_ for the most up-to-date version:

.. code-block:: bash

    git clone https://github.com/ApeWorX/ape.git
    cd ape
    python3 setup.py install

Quick Usage
***********

Ape is primarily meant to be used as a command line tool. Here are some things you do with the ``ape`` command:

.. code-block:: bash

    # Work with your accounts
    $ ape accounts list

    # Compile your project's smart contracts
    $ ape compile --size

    # Run your tests with pytest
    $ ape test -k test_only_one_thing --coverage --gas

    # Connect an IPython session through your favorite provider
    $ ape console --network ethereum:mainnet:infura

    # Add new plugins to ape
    $ ape plugins add plugin-name

Ape also works as a package. You can use the same networks, accounts, and projects from the ape package as you can in the cli:

.. code-block:: python

    # Work with registered networks, providers, and blockchain ecosystems (like Ethereum)
    from ape import networks
    with networks.ethereum.mainnet.use_provider("infura"):
        ...  # Work with the infura provider here

    # Work with test accounts, local accounts, and (WIP) popular hardware wallets
    from ape import accounts
    a = accounts[0]  # Load by index
    a = accounts["example.eth"]  # or load by ENS/address
    a = accounts.load("alias") # or load by alias

    # Work with contract types
    from ape import project
    c = a.deploy(project.MyContract, ...)
    c.viewThis()  # Make Web3 calls
    c.doThat({"from": a})  # Make Web3 transactions
    assert c.MyEvent[-1].caller == a  # Search through Web3 events
