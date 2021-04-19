from copy import deepcopy
from typing import Dict, List, Optional

import dataclassy as dc


# TODO link references & link values are for solidity, not used with Vyper
# Offsets are for dynamic links, e.g. doggie's proxy forwarder
@dc.dataclass()
class LinkDependency:
    offsets: List[int]
    type: str
    value: str


@dc.dataclass()
class LinkReference:
    offsets: List[int]
    length: int
    name: Optional[str]

    @classmethod
    def from_dict(cls, data: Dict) -> "LinkReference":
        data = deepcopy(data)
        if "name" not in data:
            data["name"] = None
        return LinkReference(**data)  # type: ignore

    def to_dict(self) -> Dict:
        data = dc.asdict(self)
        if self.name is None:
            del data["name"]
        return data


@dc.dataclass()
class Bytecode:
    bytecode: str
    linkReferences: Optional[List[LinkReference]] = None
    linkDependencies: Optional[List[LinkDependency]] = None

    @classmethod
    def from_dict(cls, data: Dict) -> "Bytecode":
        data = deepcopy(data)
        if data.get("linkReferences"):
            data["linkReferences"] = [LinkReference.from_dict(lr) for lr in data["linkReferences"]]
        else:
            data["linkReferences"] = None
        if data.get("linkDependencies"):
            data["linkDependencies"] = [
                LinkDependency(**lr) for lr in data["linkDependencies"]  # type: ignore
            ]
        else:
            data["linkDependencies"] = None
        return Bytecode(**data)  # type: ignore

    def to_dict(self) -> Dict:
        data = dc.asdict(self)
        if self.linkReferences is None:
            del data["linkReferences"]
        else:
            data["linkReferences"] = [lr.to_dict() for lr in self.linkReferences]
        if self.linkDependencies is None:
            del data["linkDependencies"]
        return data


@dc.dataclass()
class ContractInstance:
    contractType: str
    address: str
    transaction: Optional[str] = None
    block: Optional[str] = None
    runtimeBytecode: Optional[Bytecode] = None

    @classmethod
    def from_dict(cls, data: Dict) -> "ContractInstance":
        data = deepcopy(data)
        if "transaction" not in data:
            data["transaction"] = None
        if "block" not in data:
            data["block"] = None
        if data.get("runtimeBytecode"):
            data["runtimeBytecode"] = Bytecode.from_dict(data["runtimeBytecode"])
        else:
            data["runtimeBytecode"] = None
        return ContractInstance(**data)  # type: ignore

    def to_dict(self) -> Dict:
        data = dc.asdict(self)
        if self.transaction is None:
            del data["transaction"]
        if self.block is None:
            del data["block"]
        if self.runtimeBytecode is None:
            del data["runtimeBytecode"]
        else:
            data["runtimeBytecode"] = self.runtimeBytecode.to_dict()
        return data


@dc.dataclass()
class Compiler:
    name: str
    version: str
    settings: Optional[str] = None
    contractTypes: Optional[List[str]] = None

    @classmethod
    def from_dict(cls, data: Dict) -> "Compiler":
        data = deepcopy(data)
        if "settings" not in data:
            data["settings"] = None
        if "contractTypes" not in data:
            data["contractTypes"] = None
        return Compiler(**data)  # type: ignore

    def to_dict(self) -> Dict:
        data = dc.asdict(self)
        if self.settings is None:
            del data["settings"]
        if self.contractTypes is None:
            del data["contractTypes"]
        return data


@dc.dataclass()
class ContractType:
    contractName: str
    sourceId: Optional[str] = None
    deploymentBytecode: Optional[Bytecode] = None
    runtimeBytecode: Optional[Bytecode] = None
    # abi, userdoc and devdoc must conform to spec
    abi: Optional[str] = None
    userdoc: Optional[str] = None
    devdoc: Optional[str] = None

    @classmethod
    def from_dict(cls, data: Dict) -> "ContractType":
        data = deepcopy(data)
        if "sourceId" not in data:
            data["sourceId"] = None
        if data.get("deploymentBytecode"):
            data["deploymentBytecode"] = Bytecode.from_dict(data["deploymentBytecode"])
        else:
            data["deploymentBytecode"] = None
        if data.get("runtimeBytecode"):
            data["runtimeBytecode"] = Bytecode.from_dict(data["runtimeBytecode"])
        else:
            data["runtimeBytecode"] = None
        if "abi" not in data:
            data["abi"] = None
        if "userdoc" not in data:
            data["userdoc"] = None
        if "devdoc" not in data:
            data["devdoc"] = None
        return ContractType(**data)  # type: ignore

    def to_dict(self) -> Dict:
        data = dc.asdict(self)
        if self.sourceId is None:
            del data["sourceId"]
        if self.deploymentBytecode is None:
            del data["deploymentBytecode"]
        else:
            data["deploymentBytecode"] = self.deploymentBytecode.to_dict()
        if self.runtimeBytecode is None:
            del data["runtimeBytecode"]
        else:
            data["runtimeBytecode"] = self.runtimeBytecode.to_dict()
        if self.abi is None:
            del data["abi"]
        if self.userdoc is None:
            del data["userdoc"]
        if self.devdoc is None:
            del data["devdoc"]
        return data


@dc.dataclass()
class Checksum:
    algorithm: str
    hash: str


@dc.dataclass()
class Source:
    checksum: Checksum
    urls: List[str]
    content: str
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

        import urllib.request

        response = urllib.request.urlopen(self.urls[0])
        self.content = response.read().decode("utf-8")

    @classmethod
    def from_dict(cls, data: Dict) -> "Source":
        data = deepcopy(data)
        if data.get("checksum"):
            data["checksum"] = Checksum(**data["checksum"])  # type: ignore
        else:
            data["checksum"] = None
        if "urls" not in data:
            data["urls"] = None
        if "content" not in data:
            data["content"] = None
        if "installPath" not in data:
            data["installPath"] = None
        if "type" not in data:
            data["type"] = None
        if "license" not in data:
            data["license"] = None
        return Source(**data)  # type: ignore

    def to_dict(self) -> Dict:
        data = dc.asdict(self)
        if self.installPath is None:
            del data["installPath"]
        if self.type is None:
            del data["type"]
        if self.license is None:
            del data["license"]
        return data
