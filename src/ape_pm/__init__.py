from ape import plugins

from .compiler import InterfaceCompiler
from .dependency import GithubDependency, LocalDependency, NpmDependency, PythonDependency
from .projects import BrownieProject, FoundryProject


@plugins.register(plugins.CompilerPlugin)
def register_compiler():
    return (".json",), InterfaceCompiler


@plugins.register(plugins.DependencyPlugin)
def dependencies():
    yield "github", GithubDependency
    yield "local", LocalDependency
    yield "npm", NpmDependency
    yield "python", PythonDependency


@plugins.register(plugins.ProjectPlugin)
def projects():
    yield BrownieProject
    yield FoundryProject


__all__ = [
    "BrownieProject",
    "FoundryProject",
    "GithubDependency",
    "InterfaceCompiler",
    "LocalDependency",
    "NpmDependency",
    "PythonDependency",
]
