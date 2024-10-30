def __getattr__(name: str):
    if name == "AccountManager":
        from ape.managers.accounts import AccountManager

        return AccountManager

    elif name == "ChainManager":
        from ape.managers.chain import ChainManager

        return ChainManager

    elif name == "CompilerManager":
        from ape.managers.compilers import CompilerManager

        return CompilerManager

    elif name == "ConfigManager":
        from ape.managers.config import ConfigManager

        return ConfigManager

    elif name == "ConversionManager":
        from ape.managers.converters import ConversionManager

        return ConversionManager

    elif name == "NetworkManager":
        from ape.managers.networks import NetworkManager

        return NetworkManager

    elif name == "PluginManager":
        from ape.managers.plugins import PluginManager

        return PluginManager

    elif name == "ProjectManager":
        from ape.managers.project import ProjectManager

        return ProjectManager

    elif name == "QueryManager":
        from ape.managers.query import QueryManager

        return QueryManager

    else:
        raise AttributeError(name)
