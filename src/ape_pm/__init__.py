from ape import plugins

from .compiler import InterfaceCompiler
from .dependency import GithubDependency, LocalDependency, NpmDependency
from .projects import BrownieProject


@plugins.register(plugins.CompilerPlugin)
def register_compiler():
    return (".json",), InterfaceCompiler


@plugins.register(plugins.DependencyPlugin)
def dependencies():
    yield "github", GithubDependency
    yield "local", LocalDependency
    yield "npm", NpmDependency


@plugins.register(plugins.ProjectPlugin)
def projects():
    yield BrownieProject


__all__ = [
    "BrownieProject",
    "GithubDependency",
    "InterfaceCompiler",
    "LocalDependency",
    "NpmDependency",
]
