import urllib.request
from copy import deepcopy
from typing import Dict, List, Optional, Set, Union

from ape.utils import compute_checksum

from .abstract import FileMixin, SerializableType, update_list_params, update_params


# TODO link references & link values are for solidity, not used with Vyper
# Offsets are for dynamic links, e.g. EIP1167 proxy forwarder
class LinkDependency(SerializableType):
    offsets: List[int]
    type: str
    value: str


class LinkReference(SerializableType):
    offsets: List[int]
    length: int
    name: Optional[str] = None


class Bytecode(SerializableType):
    """
    Serializable data representing the byte-code of a smart-contract.
    """

    bytecode: Optional[str] = None
    """The raw byte-code ``str``."""

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

    @classmethod
    def from_dict(cls, params: Dict):
        params = deepcopy(params)
        update_list_params(params, "linkReferences", LinkReference)
        update_list_params(params, "linkDependencies", LinkDependency)
        return cls(**params)  # type: ignore


class ContractInstance(SerializableType):
    """
    Serializable data representing a contract instance.
    """

    contractType: str
    """The name of the type of smart-contract."""

    address: str
    """The address of the smart-contract."""

    transaction: Optional[str] = None
    """The deployment transaction-hash for the smart-contract."""

    block: Optional[str] = None
    """The block containing the smart-contract deployment."""

    runtimeBytecode: Optional[Bytecode] = None
    """The :class:`~ape.types.contract.Bytecode` of the smart-contract."""

    @classmethod
    def from_dict(cls, params: Dict):
        params = deepcopy(params)
        update_params(params, "runtimeBytecode", Bytecode)
        return cls(**params)  # type: ignore


class Compiler(SerializableType):
    """
    Serializable data representing a compiler.
    """

    name: str
    version: str
    """The compiler version."""

    settings: Optional[str] = None
    contractTypes: Optional[List[str]] = None


class ABIType(SerializableType):
    name: str = ""
    indexed: Optional[bool] = None
    type: Union[str, "ABIType"]
    """The type, as defined in the contract, such as ``int`` or ``bool``."""

    internalType: Optional[str] = None
    """The real type used in the byte-code, such as ``uint256`` or ``bool``."""

    @property
    def canonical_type(self) -> str:
        """
        The lower-level type. For example, the type may be ``uint`` in the code,
        but at compile-time, it gets replaced with ``uint256``.

        Returns:
            str
        """

        if isinstance(self.type, str):
            return self.type

        else:
            return self.type.canonical_type


class ABI(SerializableType):
    """
    The "Application Binary Interface" as a serializable data-structure.
    """

    name: str = ""
    inputs: List[ABIType] = []
    """
    A list of :class:`~ape.types.contract.ABIType` instances representing arguments
    to the method.
    """

    outputs: List[ABIType] = []
    """
    A list of :class:`~ape.types.contract.ABIType` instances representing return values
    from the method.
    """

    # ABI v2 Field
    # NOTE: Only functions have this field
    stateMutability: Optional[str] = None
    # NOTE: Only events have this field
    anonymous: Optional[bool] = None
    # TODO: Handle events and functions separately (maybe also default and constructor)
    #       Would parse based on value of type here, so some indirection required
    #       Might make most sense to add to ``ContractType`` as a serde extension
    type: str
    """The type of the ABI, such as ``"function"`` or ``"event"``."""

    @property
    def signature(self) -> str:
        """
        String representing the function/event signature, which includes the arg names and types,
        and output names (if any) and type(s).

        Returns:
            str
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
        A string representing the function selector, used to compute ``method_id`` and ``event_id``.

        Returns:
            str
        """
        name = self.name if (self.type == "function" or self.type == "event") else self.type
        input_names = ",".join(i.canonical_type for i in self.inputs)
        return f"{name}({input_names})"

    @property
    def is_event(self) -> bool:
        """
        ``True`` when this ABI refers to an event.
        """

        return self.anonymous is not None

    @property
    def is_payable(self) -> bool:
        """
        ``True`` when this ABI refers to a payable function.
        """

        return self.stateMutability == "payable"

    @property
    def is_stateful(self) -> bool:
        """
        ``True`` when this ABI refers to a function that may alter the state
        of the contract, such as updating a list.
        """

        return self.stateMutability not in ("view", "pure")

    @classmethod
    def from_dict(cls, params: Dict):
        params = deepcopy(params)

        # Handle ABI v1 fields (convert to ABI v2)
        if "anonymous" not in params and "stateMutability" not in params:
            if params.get("constant", False):
                params["stateMutability"] = "view"

            elif params.get("payable", False):
                params["stateMutability"] = "payable"

            else:
                params["stateMutability"] = "nonpayable"

            if "constant" in params:
                params.pop("constant")

            elif "payable" in params:
                params.pop("payable")

        update_list_params(params, "inputs", ABIType)
        update_list_params(params, "outputs", ABIType)
        return cls(**params)  # type: ignore


class ContractType(FileMixin, SerializableType):
    """
    A serializable type representing the type of a contract.
    For example, if you define your contract as ``contract MyContract`` (in Solidity),
    then ``MyContract`` would be the type.
    """

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
        """
        The constructor of the contract, if it has one. For example,
        your smart-contract (in Solidity) may define a ``constructor() public {}``.
        This property contains information about the parameters needed to initialize
        a contract.
        """

        for abi in self.abi:
            if abi.type == "constructor":
                return abi

        return None

    @property
    def fallback(self) -> Optional[ABI]:
        """
        The fallback method of the contract, if it has one. A fallback method
        is external, has no name, arguments, or return value, and gets invoked
        when the user attempts to call a method that does not exist.
        """

        for abi in self.abi:
            if abi.type == "fallback":
                return abi

        return None

    @property
    def events(self) -> List[ABI]:
        """
        The events defined in a smart contract.

        Returns:
            List[:class:`~ape.types.contract.ABI`]
        """

        return [abi for abi in self.abi if abi.type == "event"]

    @property
    def calls(self) -> List[ABI]:
        """
        The call-methods (read-only method, non-payable methods) defined in a smart contract.

        Returns:
            List[:class:`~ape.types.contract.ABI`]
        """

        return [abi for abi in self.abi if abi.type == "function" and not abi.is_stateful]

    @property
    def transactions(self) -> List[ABI]:
        """
        The transaction-methods (stateful or payable methods) defined in a smart contract.

        Returns:
            List[:class:`~ape.types.contract.ABI`]
        """

        return [abi for abi in self.abi if abi.type == "function" and abi.is_stateful]

    @classmethod
    def from_dict(cls, params: Dict):
        params = deepcopy(params)
        update_list_params(params, "abi", ABI)
        update_params(params, "deploymentBytecode", Bytecode)
        update_params(params, "runtimeBytecode", Bytecode)
        return cls(**params)  # type: ignore


class Checksum(SerializableType):
    """
    A serializable type representing a checksum.
    """

    algorithm: str
    """The algorithm used to compute the checksum, such as ``"md5"``."""

    hash: str
    """The hash ``str``."""


class Source(SerializableType):
    """
    A serializable type representing source material.
    """

    checksum: Optional[Checksum] = None
    """
    The checksum of the source. Set by calling the method
    :meth:`~ape.types.contract.Source.compute_checksum`.
    """

    urls: List[str] = []
    """The URLs by which to obtain the source, such as IPFS URLs."""

    content: Optional[str] = None
    # TODO This was probably done for solidity, needs files cached to disk for compiling
    # If processing a local project, code already exists, so no issue
    # If processing remote project, cache them in ape project data folder
    installPath: Optional[str] = None
    type: Optional[str] = None
    """The type of source, such as ``"interface"``."""

    license: Optional[str] = None
    """The license of the source, if one exists, such as the MIT license."""

    def load_content(self):
        if len(self.urls) == 0:
            return

        response = urllib.request.urlopen(self.urls[0])
        self.content = response.read().decode("utf-8")

    def compute_checksum(self, algorithm: str = "md5", force: bool = False):
        """
        Compute the checksum if ``content`` exists but ``checksum`` doesn't
        exist yet. Or compute the checksum regardless if ``force`` is ``True``.

        Raises:
            ValueError: When the content is not yet loaded.

        Args:
            algorithm (str, optional): The algorithm to use when computing the checksum.
              Defaults to ``"md5"``.
            force (bool, optional): Set to ``True`` to force a re-check. Defaults to ``False``.
        """
        if self.checksum and not force:
            return  # skip recalculating

        if not self.content:
            raise ValueError("Content not loaded yet. Can't compute checksum.")

        self.checksum = Checksum(  # type: ignore
            hash=compute_checksum(self.content.encode("utf8"), algorithm=algorithm),
            algorithm=algorithm,
        )

    @classmethod
    def from_dict(cls, params: Dict):
        params = deepcopy(params)
        update_params(params, "checksum", Checksum)
        return cls(**params)  # type: ignore
