from ape.types.contract import (
    Bytecode,
    Checksum,
    Compiler,
    ContractInstance,
    ContractType,
    LinkDependency,
    LinkReference,
    Source,
)
from ape.types.manifest import PackageManifest, PackageMeta


def test_linkreference_to_dict():
    lr = LinkReference(None, None, None)
    lrd = lr.to_dict()
    assert isinstance(lrd, dict)
    assert "name" not in lrd

    lr = LinkReference(None, None, "name")
    lrd = lr.to_dict()
    assert "name" in lrd


def test_linkreference_from_dict():
    lr = LinkReference(None, None, None)
    lrd = lr.to_dict()
    lr = LinkReference.from_dict(lrd)
    assert isinstance(lr, LinkReference)


def test_bytecode_to_dict():
    b = Bytecode(None, None, None)
    bd = b.to_dict()
    assert isinstance(bd, dict)
    assert "linkReferences" not in bd
    assert "linkDependencies" not in bd

    lr = LinkReference(None, None, None)
    b = Bytecode(None, [lr], [])
    bd = b.to_dict()
    assert "linkReferences" in bd
    assert isinstance(bd["linkReferences"][0], dict)
    assert "linkDependencies" in bd


def test_bytecode_from_dict():
    ld = LinkDependency(None, None, None)
    lr = LinkReference(None, None, None)
    b = Bytecode(None, [lr], [ld])
    bd = b.to_dict()
    b = Bytecode.from_dict(bd)

    assert isinstance(b, Bytecode)
    assert isinstance(b.linkReferences[0], LinkReference)
    assert isinstance(b.linkDependencies[0], LinkDependency)


def test_contractinstance_from_dict():
    b = Bytecode(None, None, None)
    ci = ContractInstance(None, None, "", "", b)
    cid = ci.to_dict()
    ci = ContractInstance.from_dict(cid)
    assert isinstance(ci, ContractInstance)
    assert isinstance(ci.runtimeBytecode, Bytecode)


def test_contractinstance_to_dict():
    ci = ContractInstance(None, None, None, None, None)
    cid = ci.to_dict()
    assert isinstance(cid, dict)
    assert "transaction" not in cid
    assert "block" not in cid
    assert "runtimeBytecode" not in cid

    b = Bytecode(None, None, None)
    ci = ContractInstance(None, None, "", "", b)
    cid = ci.to_dict()
    assert "transaction" in cid
    assert "block" in cid
    assert "runtimeBytecode" in cid
    assert isinstance(cid["runtimeBytecode"], dict)


def test_compiler_from_dict():
    c = Compiler(None, None, None, None)
    cd = c.to_dict()
    c = Compiler.from_dict(cd)
    assert isinstance(c, Compiler)


def test_compiler_to_dict():
    c = Compiler(None, None, None, None)
    cd = c.to_dict()
    assert isinstance(cd, dict)
    assert "settings" not in cd
    assert "contractTypes" not in cd

    c = Compiler(None, None, "", [])
    cd = c.to_dict()
    assert "settings" in cd
    assert "contractTypes" in cd


def test_contracttype_from_dict():
    db = Bytecode(None, None, None)
    rb = Bytecode(None, None, None)
    ct = ContractType(None, None, db, rb, None, None, None)
    ctd = ct.to_dict()
    ct = ContractType.from_dict(ctd)
    assert isinstance(ct, ContractType)
    assert isinstance(ct.deploymentBytecode, Bytecode)
    assert isinstance(ct.runtimeBytecode, Bytecode)


def test_contracttype_to_dict():
    ct = ContractType(None, None, None, None, None, None, None)
    ctd = ct.to_dict()
    assert isinstance(ctd, dict)
    assert "sourceId" not in ctd
    assert "deploymentBytecode" not in ctd
    assert "runtimeBytecode" not in ctd
    assert "abi" not in ctd
    assert "userdoc" not in ctd
    assert "devdoc" not in ctd

    db = Bytecode(None, None, None)
    rb = Bytecode(None, None, None)
    ct = ContractType(None, "", db, rb, "", "", "")
    ctd = ct.to_dict()
    assert "sourceId" in ctd
    assert "deploymentBytecode" in ctd
    assert isinstance(ctd["deploymentBytecode"], dict)
    assert "runtimeBytecode" in ctd
    assert isinstance(ctd["runtimeBytecode"], dict)
    assert "abi" in ctd
    assert "userdoc" in ctd
    assert "devdoc" in ctd


def test_source_load_content():
    # TODO
    pass


def test_source_from_dict():
    c = Checksum("", "")
    s = Source(c, None, None, None, None, None)
    sd = s.to_dict()
    s = Source.from_dict(sd)
    assert isinstance(s, Source)
    assert isinstance(s.checksum, Checksum)


def test_source_to_dict():
    c = Checksum("", "")
    s = Source(c, None, None, None, None, None)
    sd = s.to_dict()
    assert isinstance(sd, dict)
    assert isinstance(sd["checksum"], dict)
    assert "installPath" not in sd
    assert "type" not in sd
    assert "license" not in sd

    s = Source(None, None, None, "", "", "")
    sd = s.to_dict()
    assert "installPath" in sd
    assert "type" in sd
    assert "license" in sd


def test_packagemeta_from_dict():
    p = PackageMeta(None, None, None, None, None)
    pd = p.to_dict()
    p = PackageMeta.from_dict(pd)
    assert isinstance(p, PackageMeta)


def test_packagemeta_to_dict():
    p = PackageMeta(None, None, None, None, None)
    pd = p.to_dict()
    assert isinstance(pd, dict)
    assert "authors" not in pd
    assert "license" not in pd
    assert "description" not in pd
    assert "keywords" not in pd
    assert "links" not in pd

    p = PackageMeta([], "", "", {}, "")
    pd = p.to_dict()
    assert "authors" in pd
    assert "license" in pd
    assert "description" in pd
    assert "keywords" in pd
    assert "links" in pd


def test_packagemanifest_from_dict():
    contractinstance = ContractInstance(None, None, None, None, None)
    deployments = {"outer": {"inner": contractinstance}}
    compiler = Compiler(None, None, None, None)
    contracttype = ContractType(None, None, None, None, None, None, None)
    source = Source(None, None, None, None, None, None)
    sources = {"source": source}
    meta = PackageMeta(None, None, None, None, None)
    p = PackageManifest(
        None, None, None, meta, sources, [contracttype], [compiler], deployments, {}
    )
    pd = p.to_dict()
    p = PackageManifest.from_dict(pd)
    assert isinstance(p, PackageManifest)
    assert isinstance(p.meta, PackageMeta)
    assert isinstance(p.sources, dict)
    assert isinstance(p.sources["source"], Source)
    assert isinstance(p.contractTypes, list)
    assert isinstance(p.contractTypes[0], ContractType)
    assert isinstance(p.compilers, list)
    assert isinstance(p.compilers[0], Compiler)
    assert isinstance(p.deployments, dict)
    assert isinstance(p.deployments["outer"], dict)
    assert isinstance(p.deployments["outer"]["inner"], ContractInstance)
    assert isinstance(p.buildDependencies, dict)


def test_packagemanifest_to_dict():
    p = PackageManifest(None, None, None, None, None, None, None, None, None)
    pd = p.to_dict()
    assert isinstance(pd, dict)
    assert "meta" not in pd
    assert "sources" not in pd
    assert "contractTypes" not in pd
    assert "compilers" not in pd
    assert "deployments" not in pd
    assert "buildDependencies" not in pd

    contractinstance = ContractInstance(None, None, None, None, None)
    deployments = {"outer": {"inner": contractinstance}}
    compiler = Compiler(None, None, None, None)
    contracttype = ContractType(None, None, None, None, None, None, None)
    source = Source(None, None, None, None, None, None)
    sources = {"source": source}
    meta = PackageMeta(None, None, None, None, None)
    p = PackageManifest(
        None, None, None, meta, sources, [contracttype], [compiler], deployments, {}
    )
    pd = p.to_dict()
    assert isinstance(pd, dict)
    assert "meta" in pd
    assert "sources" in pd
    assert "contractTypes" in pd
    assert "compilers" in pd
    assert "deployments" in pd
    assert "buildDependencies" in pd
