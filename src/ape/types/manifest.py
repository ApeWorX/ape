import json
from copy import deepcopy
from pathlib import Path
from typing import Dict, List, Optional

import dataclassy as dc

from .contract import Compiler, ContractInstance, ContractType, Source


@dc.dataclass()
class PackageMeta:
    authors: Optional[List[str]] = None
    license: Optional[str] = None
    description: Optional[str] = None
    keywords: Optional[List[str]] = None
    links: Optional[Dict[str, str]] = None

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
    meta: Optional[PackageMeta] = None
    sources: Optional[Dict[str, Source]] = None
    contractTypes: Optional[List[ContractType]] = None
    compilers: Optional[List[Compiler]] = None
    # Populated as part of ape packge, actualy deployments would all be custom scripts
    deployments: Optional[Dict[str, Dict[str, ContractInstance]]] = None
    # Sourced from ape config - e.g. OpenZeppelin.
    # Force manifest to publish everything that's not published, to keep our
    # manifest slim. Manifest will link to one we've published, not the github.
    # We maintain an 'ape registry' of popular packages, that we can link in
    # here (instead of finding potential malicious ones)
    buildDependencies: Optional[Dict[str, str]] = None

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
