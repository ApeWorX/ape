Writing Plugins
###############


Plugin Writing Quickstart
*************************
Use this project template https://github.com/ApeWorX/project-template as a reference for developing a plugin. 
Note: this template is designed for 2nd class plugins so not everything may apply. 
The template may be good to follow if you want to keep your plugin of similar quality to plugins developed by ApeWorx.
Here is an example compiler plugin: https://github.com/apeworx/ape-solidity


Overall architecture flow
*************************
    In order to create a plugin which will work with ape, you will need to 
        * define a class that subclasses the abstract methods within the ``ape`` api.
        * implement all the methods in order for it to work

Types of plugins
================
	* 1st - These are plugins that are bundled with ape core. They are built in, don't have a version, and can't be uninstallled.
	* 2nd - These plugins are maintained by ape team. They are trusted. Users and developers can pin different versions but should be aware of api changes when doing so.
	* 3rd - These are community developed plugins. These will ask if you want to install a 3rd party plugin (at your own risk). These can also be pinned like in 2nd order plugins.
	... TBD could be referenced in the user documentation or possibly live in the user documentation


Plugin Registration process flow
================================
    Ape uses ``pluggy`` for plugin management. The ``@plugins.register`` decorator hooks into ape core. 
    The plugin process looks for all local installed site packages that start with ``ape_``.
    The plugin process will loop through these potential ape plugins and see which ones have created a plugin type registration.
    If the plugin type registration is found, then ``ape`` knows that this package is a plugin and attempts to process it according to registration interface. 
	Then we have a set of registered plugins that the registration process defines it needs. The ``@hookspec`` decorator describes how the plugin works. 
    CLI registration


Compilation process flow
========================
    The project manager object is a representation of your current project, which should contain all the files the user's project will use, including ``contracts/`` folder (where contract source code is stored).
    The ``contracts/`` folder is where the compiler looks for contracts to compile.
    File extensions found within the ``contracts/`` directory determine which compiler plugin ape uses.
    The pragma spec of the compilable files within the folder is checked and then used to decide if a new compiler needs to be 
    downloaded or if the version matches one of the currently installed compiler versions. 
    The contracts are then grouped by compiler type and version and fed into the corresponding compiler to compile them. 
    These are then output as a JSON file to the ``.builds`` directory. They can then be deployed on the chain from the console or a script.

    
    Source type
        Types from types module :doc:`source types <autoapi/ape/types/contract/index.html#ape.types.contract.Source>`

    Compiler manager
        The compiler manager contains all the registered compilers. 
        Compilers subclass the compiler API object, implementing the CompilerAPI methods.
    Implement :doc:`get_versions <autoapi/ape/api/compiler/index#ape.api.compiler.CompilerAPI.get_versions>` in compile.
    CompilerAPI plugins

    ContractType type
        The compilation produces - .build
        :doc:`ContractType <autoapi/ape/types/contract/index.html#ape.types.contract.ContractType>`


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

Plugin Heirarchy
================
    TBD...


Writing CLI plugins
*******************
    CLI plugins will use the plugin registration process defined above. 
    The CLI plugins should use the ``click`` library in order to be able to supply arguments from the CLI. 

    

