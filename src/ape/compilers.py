from ape.api.compiler import CompilerAPI


def load(contract_type: str) -> CompilerAPI:
    if contract_type == "":
        raise ValueError("Cannot use empty string as contract_type!")

    from ape.plugins import plugin_manager

    for impl in plugin_manager.hook.register_compiler.get_hookimpls():
        compiler_class = impl.plugin.register_compiler()
        if compiler_class.handles(contract_type):
            return compiler_class()

    raise IndexError(f"No compiler supporting contract type `{contract_type}`.")
