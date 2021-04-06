import json
from copy import deepcopy
from pathlib import Path
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
    linkReferences: Optional[List[LinkReference]]
    linkDependencies: Optional[List[LinkDependency]]

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
    transaction: Optional[str]
    block: Optional[str]
    runtimeBytecode: Optional[Bytecode]

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
    settings: Optional[str]
    contractTypes: Optional[List[str]]

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
    sourceId: Optional[str]
    deploymentBytecode: Optional[Bytecode]
    runtimeBytecode: Optional[Bytecode]
    # abi, userdoc and devdoc must conform to spec
    abi: Optional[str]
    userdoc: Optional[str]
    devdoc: Optional[str]

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
    installPath: Optional[str]
    type: Optional[str]
    license: Optional[str]

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


@dc.dataclass()
class PackageMeta:
    authors: Optional[List[str]]
    license: Optional[str]
    description: Optional[str]
    keywords: Optional[List[str]]
    links: Optional[Dict[str, str]]

    @classmethod
    def from_dict(cls, data: Dict) -> "PackageMeta":
        data = deepcopy(data)
        if "authors" not in data:
            data["authors"] = None
        if "license" not in data:
            data["license"] = None
        if "description" not in data:
            data["description"] = None
        if "keywords" not in data:
            data["keywords"] = None
        if "links" not in data:
            data["links"] = None
        return PackageMeta(**data)  # type: ignore

    def to_dict(self) -> Dict:
        data = dc.asdict(self)
        if self.authors is None:
            del data["authors"]
        if self.license is None:
            del data["license"]
        if self.description is None:
            del data["description"]
        if self.keywords is None:
            del data["keywords"]
        if self.links is None:
            del data["links"]
        return data


@dc.dataclass()
class PackageManifest:
    manifest: str
    name: str
    version: str
    meta: Optional[PackageMeta]
    sources: Optional[Dict[str, Source]]
    contractTypes: Optional[List[ContractType]]
    compilers: Optional[List[Compiler]]
    # Populated as part of ape packge, actualy deployments would all be custom scripts
    deployments: Optional[Dict[str, Dict[str, ContractInstance]]]
    # Sourced from ape config - e.g. OpenZeppelin.
    # Force manifest to publish everything that's not published, to keep our
    # manifest slim. Manifest will link to one we've published, not the github.
    # We maintain an 'ape registry' of popular packages, that we can link in
    # here (instead of finding potential malicious ones)
    buildDependencies: Optional[Dict[str, str]]

    @classmethod
    def from_file(cls, path: Path) -> "PackageManifest":
        json_file = open(path)
        json_dict = json.load(json_file)
        json_file.close()
        return cls.from_dict(json_dict)

    @classmethod
    def from_dict(cls, data: Dict) -> "PackageManifest":
        data = deepcopy(data)
        if isinstance(data.get("meta"), dict):
            data["meta"] = PackageMeta.from_dict(data["meta"])
        else:
            data["meta"] = None
        if data["sources"]:
            data["sources"] = {n: Source.from_dict(s) for (n, s) in data["sources"].items()}
        if data["contractTypes"]:
            data["contractTypes"] = [ContractType.from_dict(c) for c in data["contractTypes"]]
        if data.get("compilers"):
            data["compilers"] = [Compiler.from_dict(c) for c in data["compilers"]]
        else:
            data["compilers"] = None
        if data.get("deployments"):
            data["deployments"] = {
                uri: {name: ContractInstance.from_dict(value) for (name, value) in pair.items()}
                for (uri, pair) in data["deployments"].items()
            }
        else:
            data["deployments"] = None
        if "buildDependencies" not in data:
            data["buildDependencies"] = None

        return PackageManifest(**data)  # type: ignore

    @classmethod
    def from_config(cls, path: Path) -> "PackageManifest":
        # TODO create manifest from ape config
        pass

    def to_file(self, path: Path):
        output = self.to_dict()
        with open(path, "w") as fp:
            json.dump(output, fp, indent=4)

    def to_dict(self) -> Dict:
        data = dc.asdict(self)
        if self.meta:
            data["meta"] = self.meta.to_dict()
        else:
            del data["meta"]
        if self.sources is None:
            del data["sources"]
        else:
            data["sources"] = {k: s.to_dict() for (k, s) in self.sources.items()}
        if self.contractTypes is None:
            del data["contractTypes"]
        else:
            data["contractTypes"] = [c.to_dict() for c in self.contractTypes]
        if self.compilers is None:
            del data["compilers"]
        else:
            data["compilers"] = [c.to_dict() for c in self.compilers]
        if self.deployments is None:
            del data["deployments"]
        else:
            data["deployments"] = {
                uri: {name: ci.to_dict() for (name, ci) in pair.items()}
                for (uri, pair) in self.deployments.items()
            }
        if self.buildDependencies is None:
            del data["buildDependencies"]
        return data
