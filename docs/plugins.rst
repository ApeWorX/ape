Writing Plugins
###############

Overall architecture flow
*************************

Plugin Registration process flow
================================
    API Object registration
    CLI registration


Compilation process flow
========================
    contracts/ folder
    Project manager contains all the items in the projects folder, 
    including the contracts folder. 
    The contracts folder is where the compiler will be looking for your contracts in order to compile them.
    The file extension is used to determine which compiler extension should be used to compile the contract code.
    
    The contracts are then grouped by compiler type and fed into the compiler to compile them.
    
    
    Source type
        types from types module :doc:`source types <autoapi/ape/types/contract/index.html#ape.types.contract.Source>`
    Compiler manager
    The compiler manager contains all the registered compilers. 
    Compilers sublass the compiler API object, implementing the CompilerAPI methods.
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
    Writing fixtures
    TBD...


Argument conversion process flow
================================
    TBD...


Writing CLI plugins
*******************