def __getattr__(name: str):
    import ape.contracts.base as module

    return getattr(module, name)


__all__ = [
    "ContractContainer",
    "ContractEvent",
    "ContractInstance",
    "ContractLog",
    "ContractNamespace",
]
