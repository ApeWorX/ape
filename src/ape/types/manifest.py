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
    # NOTE: Must not override this key
    manifest: str = "ethpm/3"
    # NOTE: `name` and `version` should appear together
    # NOTE: `name` must begin lowercase, and be comprised of only `[a-z0-9-]` chars
    # NOTE: `name` should not exceed 255 chars in length
    name: Optional[str] = None
    # NOTE: `version` should be valid SemVer
    version: Optional[str] = None
    # NOTE: `meta` should be in all published packages
    meta: Optional[PackageMeta] = None
    # NOTE: `sources` source tree should be necessary and sufficient to compile
    #       all `ContractType`s in manifest
    sources: Optional[Dict[str, Source]] = None
    # NOTE: `contractTypes` should only include types directly computed from manifest
    # NOTE: `contractTypes` should not include abstracts
    contractTypes: Optional[List[ContractType]] = None
    compilers: Optional[List[Compiler]] = None
    # NOTE: Keys must be a valid BIP122 URI chain definition
    # NOTE: Values must be a dict of `ContractType.contractName` => `ContractInstance` objects
    deployments: Optional[Dict[str, Dict[str, ContractInstance]]] = None
    # NOTE: keys must begin lowercase, and be comprised of only `[a-z0-9-]` chars
    #       (like `PackageManifest.name`)
    # NOTE: keys should not exceed 255 chars in length (like `PackageManifest.name`)
    # NOTE: values must be a Content Addressible URI that conforms to the same manifest
    #       version as `manifest`
    buildDependencies: Optional[Dict[str, str]] = None
