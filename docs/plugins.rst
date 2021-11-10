Writing Plugins
###############


Plugin Writing Quickstart
*************************
Use this `project template <https://github.com/ApeWorX/project-template>`_ as a reference for developing a plugin. 
Note: this template is designed for 2nd class plugins so not everything may apply. 
The template may be good to follow if you want to keep your plugin of similar quality to plugins developed by ApeWorX.
See `the Solidity plugin <https://github.com/apeworx/ape-solidity>`_ as an example of a compiler implementations.


Overall architecture flow
*************************
In order to create a plugin which will work with ape, you will need to 
    * define a class that subclasses the abstract methods within the ``ape`` api.
    * implement all the methods in order for it to work

Types of plugins
================
* 1st - These are plugins that are bundled with ape core. They are built in, don't have a version, and can't be uninstallled.
* 2nd - These plugins are maintained by ApeWorX. They are trusted. Users and developers can pin different versions but should be aware of api changes when doing so.
* 3rd - These are plugins developed outside the ApeWorX organization. These should be installed at your own risk. These can also be pinned like in 2nd order plugins.
... TBD could be referenced in the user documentation or possibly live in the user documentation


Plugin Registration process flow
================================
Ape uses ``pluggy`` for plugin management. The ``@plugins.register`` decorator hooks into ape core. 
The plugin process looks for all local installed site packages that start with ``ape_``.
The plugin process will loop through these potential ape plugins and see which ones have created a plugin type registration.
If the plugin type registration is found, then ``ape`` knows that this package is a plugin and attempts to process it according to registration interface. 
Then we have a set of registered plugins that the registration process defines it needs. The ``@hookspec`` decorator describes how the plugin works. 
Find out more about ``@hookspec`` in the `Pluggy documentation <https://pluggy.readthedocs.io/en/stable/index.html#specifications>`_.

CLI Registration
================
CLI registration uses ``entrypoints`` which is a built-in python registry of items declared in ``setup.py``. 
Also note that typically, ``_cli.py`` is used instead of ``__init__.py`` for the location of the Click CLI group, because it is logically separate from the Python module loading process. 
If you try to define them together and use ape as a library as well, there is a race condition in the loading process that will prevent the cli plugin from working.


Compilation process flow
========================
The project manager object is a representation of your current project, which should contain all the files the user's project will use, including ``contracts/`` folder (where contract source code is stored).
The ``contracts/`` folder is where the compiler looks for contracts to compile.
File extensions found within the ``contracts/`` directory determine which compiler plugin ape uses.
The pragma spec of the compilable files within the folder is checked and then used to decide if a new compiler needs to be 
downloaded or if the version matches one of the currently installed compiler versions. 
The contracts are then grouped by compiler type and version and fed into the corresponding compiler to compile them. 
These are then output as a JSON file to the ``.build`` directory. They can then be deployed on the chain from the console or a script.


Source type
===========
Types from types module :doc:`source types <autoapi/ape/types/contract/index.html#ape.types.contract.Source>`

Compiler manager
================
The compiler manager contains all the registered compilers. 
Compiler plugins must subclass the `CompilerAPI <autoapi/ape/api/compiler/index#ape.api.compiler.CompilerAPI>`_ object and implement all ``abstractmethod``.
Implement `get_versions <autoapi/ape/api/compiler/index#ape.api.compiler.CompilerAPI.get_versions>`_ in compile.
``get_versions`` gets a set of all the files and tell it all the versions that are needed. 
It needs to get that information to create the manifest so it can record the compilers which are required. 
From the contract types you can then initialize or deploy a contract using the contract types.
data structure source is how to get the source file from the manifest
This method should always return the same value and doesn't cache.
Compiler Manager uses the compiler api and has a list of all the compiler api subclasses. 
The compiler manager has the set of all the registered compiler plugins. 
Those compiler plugins subclass the compiler api, 
and so that's how it can call out to the plugins in order to compile files 
which are detected inside the contracts folder.

CompilerAPI plugins

ContractType type
==================
The compilation produces the __.build
The manifest is a file that describes the package. 
It describes everything that is within the package. 
The package manifest contains links to source code on ipfs, 
a heirarchy of which compilers and which versions of those compilers are used to compile files, 
contract types which come from the compiled files that you might want to use in the package.
`ContractType <autoapi/ape/types/contract/index.html#ape.types.contract.ContractType>`_


Account registration process flow
=================================
accounts manager
AccountAPI/AccountContainerAPI plugins
Signing messages and transactions via AccountAPI


Transactional process flow
==========================
networks manager
EcosystemAPI plugins
NetworkAPI plugins
ProviderAPI plugins
ExplorerAPI plugins
ContractInstance type and encoding via EcosystemAPI


Test process flow
=================
This is currently under development. We will have more documenting surrounding testing as it becomes completed.
Writing fixtures
TBD...


Argument conversion process flow
================================
CLI arguments are decoded and passed in to the application with ``click``.


Writing CLI plugins
*******************
CLI plugins will use the plugin registration process defined above. 
The CLI plugins should use the ``click`` library in order to be able to supply arguments from the CLI. 



