import urllib.request
from typing import List, Optional, Set, Union

from pydantic import BaseModel

from ape.utils import compute_checksum


# TODO link references & link values are for solidity, not used with Vyper
# Offsets are for dynamic links, e.g. EIP1167 proxy forwarder
class LinkDependency(BaseModel):
    offsets: List[int]
    type: str
    value: str


class LinkReference(BaseModel):
    offsets: List[int]
    length: int
    name: Optional[str] = None


class Bytecode(BaseModel):
    bytecode: Optional[str] = None
    linkReferences: Optional[List[LinkReference]] = None
    linkDependencies: Optional[List[LinkDependency]] = None

    def __repr__(self) -> str:
        self_str = super().__repr__()

        # Truncate bytecode for display
        if self.bytecode:
            self_str = self_str.replace(
                self.bytecode, self.bytecode[:5] + "..." + self.bytecode[-3:]
            )

        return self_str


class ContractInstance(BaseModel):
    contractType: str
    address: str
    transaction: Optional[str] = None
    block: Optional[str] = None
    runtimeBytecode: Optional[Bytecode] = None


class Compiler(BaseModel):
    name: str
    version: str
    settings: Optional[str] = None
    contractTypes: Optional[List[str]] = None


class ABIType(BaseModel):
    name: str = ""  # NOTE: Tuples don't have names by default
    indexed: Optional[bool] = None
    type: Union[str, "ABIType"]
    internalType: Optional[str] = None

    @property
    def canonical_type(self) -> str:
        if isinstance(self.type, str):
            return self.type

        else:
            return self.type.canonical_type


class ABI(BaseModel):
    name: str = ""
    inputs: List[ABIType] = []
    outputs: List[ABIType] = []
    # ABI v2 Field
    # NOTE: Only functions have this field
    stateMutability: Optional[str] = None
    # NOTE: Only events have this field
    anonymous: Optional[bool] = None
    # TODO: Handle events and functions separately (maybe also default and constructor)
    #       Would parse based on value of type here, so some indirection required
    #       Might make most sense to add to ``ContractType`` as a serde extension
    type: str

    @property
    def signature(self) -> str:
        """
        String representing the function/event signature, which includes the arg names and types,
        and output names (if any) and type(s)
        """
        name = self.name if (self.type == "function" or self.type == "event") else self.type

        def encode_arg(arg: ABIType) -> str:
            encoded_arg = arg.canonical_type
            # For events (handles both None and False conditions)
            if arg.indexed:
                encoded_arg += " indexed"
            if arg.name:
                encoded_arg += f" {arg.name}"
            return encoded_arg

        input_args = ", ".join(map(encode_arg, self.inputs))
        output_args = ""

        if self.outputs:
            output_args = " -> "
            if len(self.outputs) > 1:
                output_args += "(" + ", ".join(map(encode_arg, self.outputs)) + ")"
            else:
                output_args += encode_arg(self.outputs[0])

        return f"{name}({input_args}){output_args}"

    @property
    def selector(self) -> str:
        """
        String representing the function selector, used to compute ``method_id`` and ``event_id``.
        """
        name = self.name if (self.type == "function" or self.type == "event") else self.type
        input_names = ",".join(i.canonical_type for i in self.inputs)
        return f"{name}({input_names})"

    @property
    def is_event(self) -> bool:
        return self.anonymous is not None

    @property
    def is_payable(self) -> bool:
        return self.stateMutability == "payable"

    @property
    def is_stateful(self) -> bool:
        return self.stateMutability not in ("view", "pure")


class ContractType(BaseModel):
    _keep_fields_: Set[str] = {"abi"}
    _skip_fields_: Set[str] = {"contractName"}
    contractName: str
    sourceId: Optional[str] = None
    deploymentBytecode: Optional[Bytecode] = None
    runtimeBytecode: Optional[Bytecode] = None
    # abi, userdoc and devdoc must conform to spec
    abi: List[ABI] = []
    userdoc: Optional[str] = None
    devdoc: Optional[str] = None

    @property
    def constructor(self) -> Optional[ABI]:
        for abi in self.abi:
            if abi.type == "constructor":
                return abi

        return None

    @property
    def fallback(self) -> Optional[ABI]:
        for abi in self.abi:
            if abi.type == "fallback":
                return abi

        return None

    @property
    def events(self) -> List[ABI]:
        return [abi for abi in self.abi if abi.type == "event"]

    @property
    def calls(self) -> List[ABI]:
        return [abi for abi in self.abi if abi.type == "function" and not abi.is_stateful]

    @property
    def transactions(self) -> List[ABI]:
        return [abi for abi in self.abi if abi.type == "function" and abi.is_stateful]


class Checksum(BaseModel):
    algorithm: str
    hash: str


class Source(BaseModel):
    checksum: Optional[Checksum] = None
    urls: List[str] = []
    content: Optional[str] = None
    # TODO This was probably done for solidity, needs files cached to disk for compiling
    # If processing a local project, code already exists, so no issue
    # If processing remote project, cache them in ape project data folder
    installPath: Optional[str] = None
    type: Optional[str] = None
    license: Optional[str] = None

    def load_content(self):
        """Loads resource at ``urls`` into ``content``."""
        if len(self.urls) == 0:
            return

        response = urllib.request.urlopen(self.urls[0])
        self.content = response.read().decode("utf-8")

    def compute_checksum(self, algorithm: str = "md5", force: bool = False):
        """
        Compute the checksum if ``content`` exists but ``checksum`` doesn't
        exist yet. Or compute the checksum regardless if ``force`` is ``True``.
        """
        if self.checksum and not force:
            return  # skip recalculating

        if not self.content:
            raise ValueError("Content not loaded yet. Can't compute checksum.")

        self.checksum = Checksum(  # type: ignore
            hash=compute_checksum(self.content.encode("utf8"), algorithm=algorithm),
            algorithm=algorithm,
        )
