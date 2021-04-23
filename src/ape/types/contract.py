import urllib.request
from copy import deepcopy
from typing import Dict, List, Optional

from .abstract import SerializableType, update_list_params, update_params


# TODO link references & link values are for solidity, not used with Vyper
# Offsets are for dynamic links, e.g. doggie's proxy forwarder
class LinkDependency(SerializableType):
    offsets: List[int]
    type: str
    value: str


class LinkReference(SerializableType):
    offsets: List[int]
    length: int
    name: Optional[str] = None


class Bytecode(SerializableType):
    bytecode: Optional[str] = None
    linkReferences: Optional[List[LinkReference]] = None
    linkDependencies: Optional[List[LinkDependency]] = None

    @classmethod
    def from_dict(cls, params: Dict):
        params = deepcopy(params)
        update_list_params(params, "linkReferences", LinkReference)
        update_list_params(params, "linkDependencies", LinkDependency)
        return cls(**params)  # type: ignore


class ContractInstance(SerializableType):
    contractType: str
    address: str
    transaction: Optional[str] = None
    block: Optional[str] = None
    runtimeBytecode: Optional[Bytecode] = None

    @classmethod
    def from_dict(cls, params: Dict):
        params = deepcopy(params)
        update_params(params, "runtimeBytecode", Bytecode)
        return cls(**params)  # type: ignore


class Compiler(SerializableType):
    name: str
    version: str
    settings: Optional[str] = None
    contractTypes: Optional[List[str]] = None


class ContractType(SerializableType):
    contractName: str
    sourceId: Optional[str] = None
    deploymentBytecode: Optional[Bytecode] = None
    runtimeBytecode: Optional[Bytecode] = None
    # abi, userdoc and devdoc must conform to spec
    abi: Optional[str] = None
    userdoc: Optional[str] = None
    devdoc: Optional[str] = None

    def to_dict(self):
        data = super().to_dict()

        if "abi" in data:
            data["abi"] = self.abi  # NOTE: Don't prune this one of empty lists

        return data

    @classmethod
    def from_dict(cls, params: Dict):
        params = deepcopy(params)
        update_params(params, "deploymentBytecode", Bytecode)
        update_params(params, "runtimeBytecode", Bytecode)
        return cls(**params)  # type: ignore


class Checksum(SerializableType):
    algorithm: str
    hash: str


class Source(SerializableType):
    checksum: Optional[Checksum] = None
    urls: List[str]
    content: Optional[str] = None
    # TODO This was probably done for solidity, needs files cached to disk for compiling
    # If processing a local project, code already exists, so no issue
    # If processing remote project, cache them in ape project data folder
    installPath: Optional[str] = None
    type: Optional[str] = None
    license: Optional[str] = None

    def load_content(self):
        """loads resource at `urls` into `content`"""
        if len(self.urls) == 0:
            return

        response = urllib.request.urlopen(self.urls[0])
        self.content = response.read().decode("utf-8")

    @classmethod
    def from_dict(cls, params: Dict):
        params = deepcopy(params)
        update_params(params, "checksum", Checksum)
        return cls(**params)  # type: ignore
