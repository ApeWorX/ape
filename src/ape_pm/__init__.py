from importlib import import_module

from ape import plugins


@plugins.register(plugins.CompilerPlugin)
def register_compiler():
    compiler = import_module("ape_pm.compiler")
    return (".json",), compiler.InterfaceCompiler


@plugins.register(plugins.DependencyPlugin)
def dependencies():
    _dependencies = import_module("ape_pm.dependency")
    yield "github", _dependencies.GithubDependency
    yield "local", _dependencies.LocalDependency
    yield "npm", _dependencies.NpmDependency
    yield ("python", "pypi"), _dependencies.PythonDependency


@plugins.register(plugins.ProjectPlugin)
def projects():
    _projects = import_module("ape_pm.project")
    yield _projects.BrownieProject
    yield _projects.FoundryProject


def __getattr__(name: str):
    if name in ("BrownieProject", "FoundryProject"):
        module = import_module("ape_pm.project")
    elif name in ("GithubDependency", "LocalDependency", "NpmDependency", "PythonDependency"):
        module = import_module("ape_pm.dependency")
    else:
        module = import_module("ape_pm.compiler")

    return getattr(module, name)


__all__ = [
    "BrownieProject",
    "FoundryProject",
    "GithubDependency",
    "InterfaceCompiler",
    "LocalDependency",
    "NpmDependency",
    "PythonDependency",
]
