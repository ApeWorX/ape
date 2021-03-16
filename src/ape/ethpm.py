import dataclasses as dc
from copy import deepcopy
from typing import Dict, List
from pathlib import Path
import json

# TODO Set optional fields and remove from dict
# TODO Validate ethPM/3 standard is followed for field values
# TODO Drive manifest from ape config
# TODO Populate compiler info, generated from ape config
# TODO Tests
# TODO PR
# TODO Solidity
# TODO Build Dependencies, increase complexity of what compilers can handle

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
    name: str


@dc.dataclass()
class Bytecode:
    bytecode: str
    linkReferences: List[LinkReference]
    linkDependencies: List[LinkDependency]


@dc.dataclass()
class ContractInstance:
    contractType: str
    address: str
    transaction: str
    block: str
    runtimeBytecode: Bytecode


@dc.dataclass()
class Compiler:
    name: str
    version: str
    # settings should be an object
    settings: str
    contractTypes: List[str]


@dc.dataclass()
class ContractType:
    contractName: str
    sourceId: str
    deploymentBytecode: Bytecode
    runtimeBytecode: Bytecode
    # abi, userdoc and devdoc must conform to spec
    abi: str
    userdoc: str
    devdoc: str

    @classmethod
    def from_dict(cls, data: Dict) -> "ContractType":
        data = deepcopy(data)
        data["deploymentBytecode"] = Bytecode(**data["deploymentBytecode"])
        data["runtimeBytecode"] = Bytecode(**data["runtimeBytecode"])
        return ContractType(**data)


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
    installPath: str
    type: str
    license: str

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
        return Source(**data)


@dc.dataclass()
class PackageMeta:
    authors: List[str]
    license: str
    description: str
    keywords: List[str]
    links: Dict[str, str]


@dc.dataclass()
class PackageManifest:
    manifest: str
    name: str
    version: str
    meta: PackageMeta
    sources: Dict[str, Source]
    contractTypes: List[ContractType]
    compilers: List[Compiler]
    # Populated as part of ape packge, actualy deployments would all be custom scripts
    deployments: Dict[str, Dict[str, ContractInstance]]
    # Sourced from ape config - e.g. OpenZeppelin.
    # Force manifest to publish everything that's not published, to keep our manifest slim
    # Manifest will link to one we've published, not the github
    # We maintain an 'ape registry' of popular packages, that we can link in here (instead of finding potential malicious ones)
    buildDependencies: Dict[str, str]

    @classmethod
    def from_file(cls, path: Path) -> "PackageManifest":
        json_file = open(path)
        json_dict = json.load(json_file)
        json_file.close()
        return cls.from_dict(json_dict)

    @classmethod
    def from_dict(cls, data: Dict) -> "PackageManifest":
        data = deepcopy(data)
        data["sources"] = {n: Source.from_dict(s) for (n, s) in data["sources"].items()}
        data["contractTypes"] = [ContractType.from_dict(c) for c in data["contractTypes"]]
        return PackageManifest(**data)

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
        # TODO remove optional data from dict
        # if self.contractTypes is None:
        #     del data["contractTypes"]
        return data
