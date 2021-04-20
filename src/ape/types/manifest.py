from typing import Dict, List, Optional

from .abstract import FileMixin, SerializableType
from .contract import Compiler, ContractInstance, ContractType, Source


class PackageMeta(SerializableType):
    authors: Optional[List[str]] = None
    license: Optional[str] = None
    description: Optional[str] = None
    keywords: Optional[List[str]] = None
    links: Optional[Dict[str, str]] = None


class PackageManifest(SerializableType, FileMixin):
    manifest: str = "ethpm/3"
    name: Optional[str] = None
    version: Optional[str] = None
    meta: Optional[PackageMeta] = None
    sources: Optional[Dict[str, Source]] = None
    contractTypes: Optional[List[ContractType]] = None
    compilers: Optional[List[Compiler]] = None
    deployments: Optional[Dict[str, Dict[str, ContractInstance]]] = None
    buildDependencies: Optional[Dict[str, str]] = None
