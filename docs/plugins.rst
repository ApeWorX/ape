Writing Plugins
###############

Overall architecture flow
*************************
    In order to create a plugin which will work with ape, you will need to 
        * define a class that subclasses the abstract methods within the ``ape`` api.
        * implement all the methods in order for it to work

Plugin Registration process flow
================================
    Ape uses pluggy for plugin management. The @plugins.register decorator hooks into ape core. 
    The plugin process looks for all local installed site packages that start with ``ape_``. This doesn't use ``pip`` directly but you can think of it like ``pip``. 
    The plugin process will loop through these potential ape plugins and see which ones have created a plugin type registration.
    If the plugin type registration is found, then ``ape`` knows that this package is a plugin, and `ape` attempts to process the plugin according to registration interface. 
	Then we have a set of registered plugins that the registration process defines it needs. The @hookspec decorator describes how the plugin works. 
    API Object registration
    CLI registration


Compilation process flow
========================
    `contracts/` folder
    Project manager contains all the items in the projects folder, including the contracts folder. 
    The `contracts/` folder is where the compiler will be looking for your contracts in order to compile them.
    The file extension of files within the `contracts/` folder is used to determine which compiler extension should be used.
    The pragma spec of the compilable files within the folder is checked and then used to decide if a new compiler needs to be 
    downloaded or if the version matches one of the currently installed compiler versions. 
    The contracts are then grouped by compiler type and version and fed into the corresponding compiler to compile them. 
    These are then outputted as a json file which is placed in the `.builds` folder. They can then be deployed on the chain from the console.

    
    Source type
        Types from types module :doc:`source types <autoapi/ape/types/contract/index.html#ape.types.contract.Source>`

    Compiler manager
        The compiler manager contains all the registered compilers. 
        Compilers subclass the compiler API object, implementing the CompilerAPI methods.
    Implement :doc:`get_versions <autoapi/ape/api/compiler/index#ape.api.compiler.CompilerAPI.get_versions>` in compile.
    CompilerAPI plugins

    ContractType type
        The compilation produces - .build
        :doc:`<autoapi/ape/types/contract/index.html#ape.types.contract.ContractType>`
    Project manager


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

    

