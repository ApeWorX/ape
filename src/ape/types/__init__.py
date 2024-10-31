def __getattr__(name: str):
    if name in ("HexBytes",):
        from eth_pydantic_types import HexBytes

        return HexBytes

    elif name in (
        "ABI",
        "Bytecode",
        "Checksum",
        "Compiler",
        "ContractType",
        "PackageManifest",
        "PackageMeta",
        "Source",
    ):
        import ethpm_types

        return getattr(ethpm_types, name)

    elif name in ("Closure",):
        from ethpm_types.source import Closure

        return Closure

    elif name in ("AddressType", "RawAddress"):
        import ape.types.address as address_module

        return getattr(address_module, name)

    elif name in ("HexInt", "_LazySequence"):
        import ape.types.basic as basic_module

        return getattr(basic_module, name)

    elif name in (
        "ContractCoverage",
        "ContractSourceCoverage",
        "CoverageProject",
        "CoverageReport",
        "CoverageStatement",
    ):
        import ape.types.coverage as coverage_module

        return getattr(coverage_module, name)

    elif name in ("ContractLog", "ContractLogContainer", "LogFilter", "MockContractLog"):
        import ape.types.events as events_module

        return getattr(events_module, name)

    elif name in ("AutoGasLimit", "GasLimit"):
        import ape.types.gas as gas_module

        return getattr(gas_module, name)

    elif name in ("MessageSignature", "SignableMessage", "TransactionSignature"):
        import ape.types.signatures as sig_module

        return getattr(sig_module, name)

    elif name in ("ContractFunctionPath", "ControlFlow", "GasReport", "SourceTraceback"):
        import ape.types.trace as trace_module

        return getattr(trace_module, name)

    elif name in ("CurrencyValue", "CurrencyValueComparable"):
        import ape.types.units as units_module

        return getattr(units_module, name)

    elif name in ("BlockID", "ContractCode", "SnapshotID"):
        import ape.types.vm as vm_module

        return getattr(vm_module, name)

    elif name in (
        "BaseInterface",
        "BaseInterfaceModel",
        "BaseModel",
        "ExtraAttributesMixin",
        "ExtraModelAttributes",
        "ManagerAccessMixin",
        "get_attribute_with_extras",
        "get_item_with_extras",
        "only_raise_attribute_error",
    ):
        import ape.utils.basemodel as basemodel_module

        return getattr(basemodel_module, name)

    else:
        raise AttributeError(name)


__all__ = [
    "_LazySequence",
    "ABI",
    "AddressType",
    "AutoGasLimit",
    "BaseInterface",
    "BaseInterfaceModel",
    "BaseModel",
    "BlockID",
    "Bytecode",
    "Checksum",
    "Closure",
    "Compiler",
    "ContractCode",
    "ContractCoverage",
    "ContractFunctionPath",
    "ContractSourceCoverage",
    "ContractLog",
    "ContractLogContainer",
    "ContractType",
    "ControlFlow",
    "CoverageProject",
    "CoverageReport",
    "CoverageStatement",
    "CurrencyValue",
    "CurrencyValueComparable",
    "ExtraAttributesMixin",
    "ExtraModelAttributes",
    "GasLimit",
    "GasReport",
    "get_attribute_with_extras",
    "get_item_with_extras",
    "HexInt",
    "HexBytes",
    "LogFilter",
    "ManagerAccessMixin",
    "MessageSignature",
    "MockContractLog",
    "only_raise_attribute_error",
    "PackageManifest",
    "PackageMeta",
    "RawAddress",
    "SignableMessage",
    "SnapshotID",
    "Source",
    "SourceTraceback",
    "TransactionSignature",
]
