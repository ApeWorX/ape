from fnmatch import fnmatch
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Tuple

from ethpm_types import ASTNode, BaseModel, ContractType, HexBytes, PCMap, Source
from ethpm_types.ast import ASTClassification, SourceLocation
from evm_trace.gas import merge_reports
from pydantic import Field, validator
from rich.table import Table
from rich.tree import Tree

from ape.types.address import AddressType
from ape.utils.basemodel import BaseInterfaceModel
from ape.utils.trace import parse_as_str, parse_gas_table, parse_rich_tree

if TYPE_CHECKING:
    from ape.types import ContractFunctionPath


GasReport = Dict[str, Dict[str, List[int]]]
"""
A gas report in Ape.
"""


class CallTreeNode(BaseInterfaceModel):
    contract_id: str
    """
    The identifier representing the contract in this node.
    A non-enriched identifier is an address; a more enriched
    identifier is a token symbol or contract type name.
    """

    method_id: Optional[str] = None
    """
    The identifier representing the method in this node.
    A non-enriched identifier is a method selector.
    An enriched identifier is method signature.
    """

    txn_hash: Optional[str] = None
    """
    The transaction hash, if known and/or exists.
    """

    failed: bool = False
    """
    ``True`` where this tree represents a failed call.
    """

    inputs: Optional[Any] = None
    """
    The inputs to the call.
    Non-enriched inputs are raw bytes or values.
    Enriched inputs are decoded.
    """

    outputs: Optional[Any] = None
    """
    The output to the call.
    Non-enriched inputs are raw bytes or values.
    Enriched outputs are decoded.
    """

    value: Optional[int] = None
    """
    The value sent with the call, if applicable.
    """

    gas_cost: Optional[int] = None
    """
    The gas cost of the call, if known.
    """

    call_type: Optional[str] = None
    """
    A str indicating what type of call it is.
    See ``evm_trace.enums.CallType`` for EVM examples.
    """

    calls: List["CallTreeNode"] = []
    """
    The list of subcalls made by this call.
    """

    raw: Dict = Field({}, exclude=True, repr=False)
    """
    The raw tree, as a dictionary, associated with the call.
    """

    def __repr__(self) -> str:
        return parse_as_str(self)

    def __str__(self) -> str:
        return parse_as_str(self)

    def _repr_pretty_(self, *args, **kwargs):
        enriched_tree = self.enrich(use_symbol_for_tokens=True)
        self.chain_manager._reports.show_trace(enriched_tree)

    def enrich(self, **kwargs) -> "CallTreeNode":
        """
        Enrich the properties on this call tree using data from contracts
        and using information about the ecosystem.

        Args:
            **kwargs: Key-word arguments to pass to
              :meth:`~ape.api.networks.EcosystemAPI.enrich_calltree`, such as
              ``use_symbol_for_tokens``.

        Returns:
            :class:`~ape.types.trace.CallTreeNode`: This call tree node with
            its properties enriched.
        """

        return self.provider.network.ecosystem.enrich_calltree(self, **kwargs)

    def add(self, sub_call: "CallTreeNode"):
        """
        Add a sub call to this node. This implies this call called the sub-call.

        Args:
            sub_call (:class:`~ape.types.trace.CallTreeNode`): The sub-call to add.
        """

        self.calls.append(sub_call)

    def as_rich_tree(self, verbose: bool = False) -> Tree:
        """
        Return this object as a ``rich.tree.Tree`` for pretty-printing.

        Returns:
            ``Tree``
        """

        return parse_rich_tree(self, verbose=verbose)

    def as_gas_tables(self, exclude: Optional[List["ContractFunctionPath"]] = None) -> List[Table]:
        """
        Return this object as list of rich gas tables for pretty printing.

        Args:
            exclude (Optional[List[:class:`~ape.types.ContractFunctionPath`]]):
              A list of contract / method combinations to exclude from the gas
              tables.

        Returns:
            List[``rich.table.Table``]
        """

        report = self.get_gas_report(exclude=exclude)
        return parse_gas_table(report)

    def get_gas_report(self, exclude: Optional[List["ContractFunctionPath"]] = None) -> "GasReport":
        """
        Get a unified gas-report of all the calls made in this tree.

        Args:
            exclude (Optional[List[:class:`~ape.types.ContractFunctionPath`]]):
              A list of contract / method combinations to exclude from the gas
              tables.

        Returns:
            :class:`~ape.types.trace.GasReport`
        """

        exclusions = exclude or []

        for exclusion in exclusions:
            if exclusion.method_name is None and fnmatch(self.contract_id, exclusion.contract_name):
                # Skip this whole contract. Search contracts from sub-calls.
                return merge_reports(*(c.get_gas_report(exclude) for c in self.calls))

            for excl in exclusions:
                if not excl.method_name:
                    # Full contract skips handled above.
                    continue

                elif not fnmatch(self.contract_id, excl.contract_name):
                    # Method may match, but contract does not match, so continue.
                    continue

                elif self.method_id and fnmatch(self.method_id, excl.method_name):
                    # Skip this report because of the method name exclusion criteria.
                    return merge_reports(*(c.get_gas_report(exclude) for c in self.calls))

        reports = [c.get_gas_report(exclude) for c in self.calls]
        if self.method_id:
            report = {
                self.contract_id: {
                    self.method_id: [self.gas_cost] if self.gas_cost is not None else []
                }
            }
            reports.append(report)

        return merge_reports(*reports)


class TraceFrame(BaseInterfaceModel):
    """
    A low-level data structure modeling a transaction trace frame
    from the Geth RPC ``debug_traceTransaction``.
    """

    pc: int
    """Program counter."""

    op: str
    """Opcode."""

    gas: int
    """Remaining gas."""

    gas_cost: int
    """The cost to execute this opcode."""

    depth: int
    """
    The number of external jumps away the initially called contract (starts at 0).
    """

    contract_address: Optional[AddressType] = None
    """
    The contract address, if this is a call trace frame.
    """

    raw: Dict = Field({}, exclude=True, repr=False)
    """
    The raw trace frame from the provider.
    """


class SourceContent(BaseModel):
    """
    A wrapper around source code line numbers mapped to the content
    string of those lines.
    """

    __root__: Dict[int, str]

    @property
    def begin_lineno(self) -> int:
        return self.line_numbers[0] if self.line_numbers else -1

    @property
    def end_lineno(self) -> int:
        return self.line_numbers[-1] if self.line_numbers else -1

    @property
    def line_numbers(self) -> List[int]:
        """
        All line number in order for this piece of content.
        """
        return sorted(list(self.__root__.keys()))

    def items(self):
        return self.__root__.items()

    def as_list(self) -> List[str]:
        return list(self.__root__.values())

    def __getitem__(self, lineno: int) -> str:
        return self.__root__[lineno]

    def __iter__(self):
        yield from self.__root__

    def __len__(self) -> int:
        return len(self.__root__)


class Closure(BaseModel):
    """
    A wrapper around code ran, such as a function.
    """

    name: str
    """The name of the definition."""


class SourceFunction(Closure):
    """
    Data about a function in a contract with known source code.
    """

    ast: ASTNode
    """The function definition AST node."""

    offset: int
    """The line number of the first AST after the signature."""

    content: SourceContent
    """The function's line content after the signature, mapped by line numbers."""

    @validator("ast", pre=True)
    def validate_ast(cls, value):
        if (
            value.classification is not ASTClassification.FUNCTION
            or "function" not in str(value.ast_type).lower()
        ):
            raise ValueError(
                f"`ast` must be a function definition (classification={value.classification})."
            )

        return value

    def __str__(self) -> str:
        return self.name

    def __repr__(self) -> str:
        preview = self.name[:18].rstrip()
        return f"<SourceFunction {preview} ... >"

    def get_content(self, location: SourceLocation) -> SourceContent:
        """
        Get the source content for the given location.

        Args:
            location (``SourceLocation``): The location of the content.

        Returns:
            :class:`~ape.types.trace.SourceContent`
        """

        start = max(location[0], self.offset)
        stop = location[2] + 1
        content = {n: self.content[n] for n in range(start, stop) if n in self.content}
        return SourceContent(__root__=content)

    def get_content_asts(self, location: SourceLocation) -> List[ASTNode]:
        """
        Get all AST nodes for the given location.

        Args:
            location (``SourceLocation``): The location of the content.

        Returns:
            ``List[ASTNode]``: AST nodes objects.
        """

        return [
            a
            for a in self.ast.get_nodes_at_line(location)
            if a.lineno >= location[0] and a.classification is not ASTClassification.FUNCTION
        ]


class Statement(BaseModel):
    """
    A class representing an item in a control flow, either a source statement
    or implicit compiler code.
    """

    type: str

    def __repr__(self) -> str:
        return f"<Statement type={self.type}>"


class SourceStatement(Statement):
    """
    A class mapping an AST node to some source code content.
    """

    type: str = "source"

    asts: List[ASTNode]
    """The AST nodes from this statement."""

    content: SourceContent
    """The source code content connected to the AST node."""

    @validator("content", pre=True)
    def validate_content(cls, value):
        if len(value) < 1:
            raise ValueError("Must have at least 1 line of content.")

        return value

    @validator("asts", pre=True)
    def validate_asts(cls, value):
        if len(value) < 1:
            raise ValueError("Must have at least 1 AST node.")

        return value

    @property
    def begin_lineno(self) -> int:
        """
        The first line number.
        """

        return self.asts[0].lineno

    @property
    def ws_begin_lineno(self) -> int:
        """
        The first line number including backfilled whitespace lines
        (for output debugging purposes).
        """

        # NOTE: Whitespace only include when above or besides a statement;
        # not below.

        # Whitespace lines should already be present in content.
        return self.content.begin_lineno

    @property
    def end_lineno(self) -> int:
        """
        The last line number.
        """

        return self.asts[-1].end_lineno

    @property
    def location(self) -> SourceLocation:
        return self.begin_lineno, -1, self.end_lineno, -1

    def __str__(self) -> str:
        # Include whitespace lines.
        return self.to_str()

    def __repr__(self) -> str:
        # Excludes whitespace lines.
        return self.to_str(begin_lineno=self.begin_lineno)

    def to_str(self, begin_lineno: Optional[int] = None):
        begin_lineno = self.ws_begin_lineno if begin_lineno is None else begin_lineno
        content = ""
        for lineno, line in self.content.items():
            if lineno < begin_lineno:
                continue

            elif content:
                # Indent first.
                content = f"{content.rstrip()}\n"

            content = f"{content}    {lineno} {line}"

        return content


class ControlFlow(BaseModel):
    """
    A collection of linear source nodes up until a jump.
    """

    statements: List[Statement]
    """
    The source node statements.
    """

    closure: Closure
    """
    The defining closure, such as a function or module, of the code sequence.
    """

    source_path: Path
    """
    The path to the local contract file.
    Only exists when is from a local contract.
    """

    depth: int
    """
    The depth at which this flow was executed,
    where 1 is the first calling function.
    """

    def __str__(self) -> str:
        return f"{self.source_header}\n{self.format()}"

    def __repr__(self) -> str:
        representation = f"<control path, {self.source_path.name} {self.closure.name}"

        if len(self.statements) > 0:
            representation = f"{representation} num_statements={len(self.statements)}"

        if self.begin_lineno is None:
            return f"{representation}>"

        else:
            # Include line number info.
            end_lineno = self.end_lineno or self.begin_lineno
            line_range = (
                f"line {self.begin_lineno}"
                if self.begin_lineno == end_lineno
                else f"lines {self.begin_lineno}-{end_lineno}"
            )
            return f"{representation}, {line_range}>"

    def __getitem__(self, idx: int) -> Statement:
        try:
            return self.statements[idx]
        except IndexError as err:
            raise IndexError(f"Statement index '{idx}' out of range.") from err

    @property
    def source_statements(self) -> List[SourceStatement]:
        """
        All statements coming directly from a contract's source.
        Excludes implicit-compiler statements.
        """
        return [x for x in self.statements if isinstance(x, SourceStatement)]

    @property
    def begin_lineno(self) -> Optional[int]:
        """
        The first line number in the sequence.
        """
        stmts = self.source_statements
        return stmts[0].begin_lineno if stmts else None

    @property
    def ws_begin_lineno(self) -> Optional[int]:
        """
        The first line number in the sequence, including whitespace.
        """
        stmts = self.source_statements
        return stmts[0].ws_begin_lineno if stmts else None

    @property
    def line_numbers(self) -> List[int]:
        """
        The list of all line numbers as part of this node.
        """

        if self.begin_lineno is None:
            return []

        elif self.end_lineno is None:
            return [self.begin_lineno]

        return list(range(self.begin_lineno, self.end_lineno + 1))

    @property
    def content(self) -> SourceContent:
        result: Dict[int, str] = {}
        for node in self.source_statements:
            result = {**result, **node.content.__root__}

        return SourceContent(__root__=result)

    @property
    def source_header(self) -> str:
        return f"File {self.source_path}, in {self.closure.name}".rstrip()

    @property
    def end_lineno(self) -> Optional[int]:
        """
        The last line number.
        """
        stmts = self.source_statements
        return stmts[-1].end_lineno if stmts else None

    def extend(self, location: SourceLocation, ws_start: Optional[int] = None):
        """
        Extend this node's content with other content that follows it directly.

        Raises:
            ValueError: When there is a gap in content.

        Args:
            location (SourceLocation): The location of the content, in the form
              (lineno, col_offset, end_lineno, end_coloffset).
            ws_start (Optional[int]): Optionally provide a white-space starting point
              to back-fill.
        """

        if ws_start is not None and ws_start > location[0]:
            # No new lines.
            return

        function = self.closure
        if not isinstance(function, SourceFunction):
            # No source code supported for closure type.
            return

        # NOTE: Use non-ws prepending location to fetch AST nodes.
        asts = function.get_content_asts(location)
        if not asts:
            return

        location = (
            (ws_start, location[1], location[2], location[3]) if ws_start is not None else location
        )
        content = function.get_content(location)
        start = (
            max(location[0], self.end_lineno + 1) if self.end_lineno is not None else location[0]
        )
        end = location[0] + len(content) - 1
        if end < start:
            # No new lines.
            return

        elif start - end > 1:
            raise ValueError(
                "Cannot extend when gap in lines > 1. "
                "If because of whitespace lines, must include it the given content."
            )

        content_start = len(content) - (end - start) - 1
        new_lines = {no: ln.rstrip() for no, ln in content.items() if no >= content_start}
        if new_lines:
            # Add the next statement in this sequence.
            content = SourceContent(__root__=new_lines)
            statement = SourceStatement(asts=asts, content=content)
            self.statements.append(statement)

        else:
            # Add ASTs to latest statement.
            self.source_statements[-1].asts.extend(asts)

    def format(self, use_arrow: bool = True) -> str:
        """
        Format this trace node into a string presentable to the user.
        """

        # NOTE: Only show last 2 statements.
        relevant_stmts = self.statements[-2:]
        content = ""
        end_lineno = self.content.end_lineno

        for stmt in relevant_stmts:
            for lineno, line in getattr(stmt, "content", {}).items():
                if not content and not line.strip():
                    # Prevent starting on whitespace.
                    continue

                if content:
                    # Add newline to carry over from last.
                    content = f"{content.rstrip()}\n"

                space = "       " if lineno < end_lineno or not use_arrow else "  -->  "
                content = f"{content}{space}{lineno} {line}"

        return content

    @property
    def next_statement(self) -> Optional[SourceStatement]:
        """
        Returns the next statement that _would_ execute
        if the program were to progress to the next line.
        """

        # Check for more statements that _could_ execute.
        if not self.statements:
            return None

        last_stmt = self.source_statements[-1]
        function = self.closure
        if not isinstance(function, SourceFunction):
            return None

        rest_asts = [a for a in function.ast.children if a.lineno > last_stmt.end_lineno]
        if not rest_asts:
            # At the end of a function.
            return None

        # Filter out to only the ASTs for the next statement.
        next_stmt_start = min(rest_asts, key=lambda x: x.lineno).lineno
        next_stmt_asts = [a for a in rest_asts if a.lineno == next_stmt_start]
        content_dict = {}
        for ast in next_stmt_asts:
            sub_content = function.get_content(ast.line_numbers)
            content_dict = {**sub_content.__root__}

        if not content_dict:
            return None

        sorted_dict = {k: content_dict[k] for k in sorted(content_dict)}
        content = SourceContent(__root__=sorted_dict)
        return SourceStatement(asts=next_stmt_asts, content=content)


class SourceTraceback(BaseModel):
    """
    A full execution traceback including source code.
    """

    __root__: List[ControlFlow]

    def __str__(self) -> str:
        return self.format()

    def __repr__(self) -> str:
        return f"<ape.types.SourceTraceback control_paths={len(self.__root__)}>"

    def __len__(self) -> int:
        return len(self.__root__)

    def __iter__(self):
        yield from self.__root__

    def __getitem__(self, idx: int) -> ControlFlow:
        try:
            return self.__root__[idx]
        except IndexError as err:
            raise IndexError(f"Control flow index '{idx}' out of range.") from err

    def __setitem__(self, key, value):
        return self.__root__.__setitem__(key, value)

    def append(self, __object) -> None:
        self.__root__.append(__object)

    def extend(self, __iterable) -> None:
        if not isinstance(__iterable, SourceTraceback):
            raise TypeError("Can only extend another traceback object.")

        self.__root__.extend(__iterable.__root__)

    @property
    def last(self) -> Optional[ControlFlow]:
        return self.__root__[-1] if len(self.__root__) else None

    @property
    def execution(self) -> List[ControlFlow]:
        return list(self.__root__)

    def format(self) -> str:
        if not len(self.__root__):
            # No calls.
            return ""

        header = "Traceback (most recent call last)"
        indent = "  "
        last_depth = None
        segments = []
        for control_flow in reversed(self.__root__):
            if last_depth is None or control_flow.depth == last_depth - 1:
                last_depth = control_flow.depth
                segment = f"{indent}{control_flow.source_header}\n{control_flow.format()}"

                # Try to include next statement for display purposes.
                next_stmt = control_flow.next_statement
                if next_stmt:
                    if (
                        next_stmt.begin_lineno is not None
                        and control_flow.end_lineno is not None
                        and next_stmt.begin_lineno > control_flow.end_lineno + 1
                    ):
                        # Include whitespace.
                        for ws_no in range(control_flow.end_lineno + 1, next_stmt.begin_lineno):
                            function = control_flow.closure
                            if not isinstance(function, SourceFunction):
                                continue

                            ws = function.content[ws_no]
                            segment = f"{segment}\n       {ws_no} {ws}".rstrip()

                    for no, line in next_stmt.content.items():
                        segment = f"{segment}\n       {no} {line}".rstrip()

                segments.append(segment)

        builder = ""
        for idx, segment in enumerate(reversed(segments)):
            builder = f"{builder}\n{segment}"

            if idx < len(segments) - 1:
                builder = f"{builder}\n"

        return f"{header}{builder}"

    def add_jump(
        self, location: SourceLocation, function: SourceFunction, source_path: Path, depth: int
    ):
        """
        Add an execution sequence from a jump.

        Args:
            location (``SourceLocation``): The location to add.
            function (:class:`~ape.types.trace.SourceFunction`): The function executing.
            source_path (``Path``): The path of the source file.
            depth (int): The depth of the function call in the call tree.
        """

        # Exclude signature ASTs.
        asts = function.get_content_asts(location)
        content = function.get_content(location)
        if not asts or not content:
            return

        Statement.update_forward_refs()
        ControlFlow.update_forward_refs()
        self._add(asts, content, source_path, function, depth)

    def extend_last(self, location: SourceLocation):
        """
        Extend the last node with more content.

        Args:
            location (``SourceLocation``): The location of the new content.
        """

        if not self.last:
            raise ValueError(
                "`progress()` should only be called when "
                "there is at least 1 ongoing execution trail."
            )

        start = (
            1
            if self.last is not None and self.last.end_lineno is None
            else self.last.end_lineno + 1
        )
        self.last.extend(location, ws_start=start)

    def _add(
        self,
        asts: List[ASTNode],
        content: SourceContent,
        source_path: Path,
        function: SourceFunction,
        depth: int,
    ):
        statement = SourceStatement(asts=asts, content=content)
        exec_sequence = ControlFlow(
            statements=[statement], source_path=source_path, closure=function, depth=depth
        )
        self.append(exec_sequence)


class ContractSource(BaseModel):
    """
    A contract type wrapper that enforces all the necessary
    properties needed for doing source-code processing,
    such as coverage or showing source code lines during an exception.
    """

    contract_type: ContractType
    """The contract type with AST, PCMap, and other necessary properties."""

    source: Source
    """The source code wrapper."""

    source_path: Path
    """The path to the source."""

    _function_ast_cache: Dict[str, ASTNode] = {}

    @validator("contract_type", pre=True)
    def _validate_contract_type(cls, contract_type):
        if contract_type.source_id is None:
            raise ValueError("ContractType missing source_id")
        if contract_type.ast is None:
            raise ValueError("ContractType missing ast")
        if contract_type.pcmap is None:
            raise ValueError("ContractType missing pcmap")

        return contract_type

    @property
    def source_id(self) -> str:
        """The contract type source ID."""

        return self.contract_type.source_id  # type: ignore[return-value]

    @property
    def ast(self) -> ASTNode:
        """The contract type AST node."""

        return self.contract_type.ast  # type: ignore[return-value]

    @property
    def pcmap(self) -> PCMap:
        """The contract type PCMap."""

        return self.contract_type.pcmap  # type: ignore[return-value]

    def __repr__(self) -> str:
        return f"<{self.source_path.name}::{self.contract_type.name or 'unknown'}>"

    def lookup_function(
        self, location: SourceLocation, method_id: Optional[HexBytes] = None
    ) -> Optional[SourceFunction]:
        """
        Lookup a function by location.

        Args:
            location (``SourceLocation``): The location to search.
            method_id (Optional[HexBytes]): Optionally provide a method ID
              to use to craft a nicer name. Defaults to using the combined
              lines of the function signature content.

        Returns:
            Optional[:class:`~ape.types.trace.SourceFunction`]: The function, if one is
            found.
        """

        ast = self.ast.get_defining_function(location)
        if not ast:
            return None

        signature_lines, content_lines = self._parse_function(ast)
        offset = ast.lineno + len(signature_lines)

        # Check if method ID points to a calling method.
        name = None
        if method_id and method_id.hex() in self._function_ast_cache:
            cached_fn = self._function_ast_cache[method_id.hex()]
            if (
                cached_fn.lineno == ast.lineno
                and cached_fn.end_lineno == ast.end_lineno
                and method_id in self.contract_type.methods
            ):
                # Is the same function. It's safe to use the method ABI name.
                method = self.contract_type.methods[method_id]
                name = method.name

        elif method_id and method_id in self.contract_type.methods:
            # Not in cache yet. Assume is calling.
            method = self.contract_type.methods[method_id]
            name = method.name
            self._function_ast_cache[method_id.hex()] = ast

        if name is None:
            name = "".join([x.strip() for x in signature_lines]).rstrip()

        content_dict = {offset + i: ln for i, ln in enumerate(content_lines)}
        content = SourceContent(__root__=content_dict)
        SourceFunction.update_forward_refs()

        return SourceFunction(
            ast=ast,
            name=name,
            offset=offset,
            content=content,
        )

    def _parse_function(self, function: ASTNode) -> Tuple[List[str], List[str]]:
        """
        Parse function AST into two groups. One being the list of
        lines making up the signature and the other being the content
        lines of the function.
        """

        start = function.lineno - 1
        end = function.end_lineno
        lines = self.source[start:end]

        content_start = None
        for child in function.children:
            # Find smallest lineno after signature-related ASTs.
            if (
                child.lineno > function.lineno
                and child.classification != ASTClassification.FUNCTION
                and (content_start is None or child.lineno < content_start)
            ):
                content_start = child.lineno

        if content_start is None:
            # Shouldn't happen, but just in case, use only the first line.
            content_start = function.lineno + 1

        offset = content_start - function.lineno
        return lines[:offset], lines[offset:]
