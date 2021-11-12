Quickstart Guide
################

Prerequisite
************

In the latest release, Ape requires: 

**Linux or macOS**
* Python 3.7.X or later

**Windows**: 

#. Install Windows Subsystem Linux `(WSL) <https://docs.microsoft.com/en-us/windows/wsl/install>`_ 
#. Choose Ubuntu 20.04 OR Any other Linux Distribution with Python 3.7.X or later

Please make sure you are using Python 3.7.X or later.

.. code-block:: bash
    # check your python version
    $ python3 --version




Installation
************
**Suggestion**: Create a virtual environment via ``virtualenv`` or ``venv`` .

You may skip this creating a virtual environment if you know you don't require one for your use case. 

via ``virtualenv`` `virtualenv <https://pypi.org/project/virtualenv/>`_ or via ``venv <https://docs.python.org/3/library/venv.html>``_

============================================================

.. code-block:: bash

    # Create your virtual environment folder
    $ python3 -m venv /path/to/new/environment
    $ source <venv_folder>/bin/activate
    # you should see (name_of_venv) DESKTOP_NAME:~/path:$ 


.. code-block:: bash

    # deactivate virtual environment
    $ deactivate



Now that your Python version is later than 3.7.X and you have created a virtual environment, let's install ape!
There are 3 ways to install ape: pip, setuptools, or Docker.

via ``pip``
===========

You can install the latest release via `pip <https://pypi.org/project/pip/>`_:

.. code-block:: bash

    $ pip install eth-ape

via ``setuptools``
==================

You can clone the repository and use `setuptools <https://github.com/pypa/setuptools>`_ for the most up-to-date version:

.. code-block:: bash

    $ git clone https://github.com/ApeWorX/ape.git
    $ cd ape
    $ python3 setup.py install

via ``docker``
==============

Please visit our `Dockerhub <https://hub.docker.com/repository/docker/apeworx/ape>`_ for more details on using Ape with Docker.

.. code-block:: bash

    $ docker run \
    --volume $HOME/.ape:/root/.ape \
    --volume $HOME/.vvm:/root/.vvm \
    --volume $HOME/.solcx:/root/.solcx \
    --volume $PWD:/root/project \
    --workdir /root/project \
    apeworx/ape compile


When switching back and forth between docker and normal ape you may have permissions issues. 
To resolve these you can use either of the following solutions:
1. ``chown ~/.solcx && chown ~/.solcx``
2. ``sudo rm -rf ~/.solcx && sudo rm -rf ~/.vvm``


Once ape is installed you can test some of the features! Here is a guide on some of the popular
commands.

Quick Usage
***********

Ape is primarily meant to be used as a command line tool. Here are some things you do with the ``ape`` command:


.. code-block:: bash

    # List the ape commands
    $ ape -h
    
    # Generate a new test account
    $ ape accounts generate acc1

    # List existing accounts
    $ ape accounts list


.. code-block:: bash

    # You can interact and compile contracts
    # cd in to a directory with a contracts folder containing a contract.
    $ cd vyper-project/
    # You will need a compiler plugin in order to compile Vyper code
    $ ape plugins add vyper
    # Now you can compile Vyper contracts in the contracts folder of your project
    $ ape compile --size
    # Now you should see inside the .build directory your compiled json file
    $ ls .build

.. code-block:: bash

    # Should we include a way to list available plugins to install?
    # Add new plugins to ape
    $ ape plugins add plugin-name

.. code-block:: bash

    # Connect an IPython session through your favorite provider
    $ ape console --network ethereum:mainnet:infura


.. code-block:: bash

    $ ape run


Ape as a package works both in ``ape run`` scripts and it also can be used in other python programs via import. 
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

.. code-block:: bash

    # Not part of ape -h, what does -k mean, ape test does not work
    # Run your tests with pytest
    $ ape test -k test_only_one_thing --coverage --gas

