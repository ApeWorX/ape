from itertools import chain, tee
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, Iterator, List, Optional, Set, Union

from ethpm_types import ASTNode, BaseModel, ContractType, HexBytes
from ethpm_types.ast import SourceLocation
from ethpm_types.source import Closure, Content, Function, SourceStatement, Statement
from evm_trace.gas import merge_reports
from rich.table import Table
from rich.tree import Tree

from ape._pydantic_compat import Field
from ape.types.address import AddressType
from ape.utils.basemodel import BaseInterfaceModel
from ape.utils.misc import is_evm_precompile, is_zero_hex
from ape.utils.trace import _exclude_gas, parse_as_str, parse_gas_table, parse_rich_tree

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
        if (
            not self.contract_id
            or not self.method_id
            or _exclude_gas(exclusions, self.contract_id, self.method_id)
        ):
            return merge_reports(*(c.get_gas_report(exclude) for c in self.calls))

        elif not is_zero_hex(self.method_id) and not is_evm_precompile(self.method_id):
            reports = [
                *[c.get_gas_report(exclude) for c in self.calls],
                {
                    self.contract_id: {
                        self.method_id: [self.gas_cost] if self.gas_cost is not None else []
                    }
                },
            ]
            return merge_reports(*reports)

        return merge_reports(*(c.get_gas_report(exclude) for c in self.calls))


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

    source_path: Optional[Path] = None
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
        source_name = f" {self.source_path.name} " if self.source_path is not None else " "
        representation = f"<control path,{source_name}{self.closure.name}"

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

    def __len__(self) -> int:
        return len(self.statements)

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
    def content(self) -> Content:
        result: Dict[int, str] = {}
        for node in self.source_statements:
            result = {**result, **node.content.__root__}

        return Content(__root__=result)

    @property
    def source_header(self) -> str:
        result = ""
        if self.source_path is not None:
            result += f"File {self.source_path}, in "

        result += f"{self.closure.name}"
        return result.strip()

    @property
    def end_lineno(self) -> Optional[int]:
        """
        The last line number.
        """
        stmts = self.source_statements
        return stmts[-1].end_lineno if stmts else None

    @property
    def pcs(self) -> Set[int]:
        full_set: Set[int] = set()
        for stmt in self.statements:
            full_set |= stmt.pcs

        return full_set

    def extend(
        self,
        location: SourceLocation,
        pcs: Optional[Set[int]] = None,
        ws_start: Optional[int] = None,
    ):
        """
        Extend this node's content with other content that follows it directly.

        Raises:
            ValueError: When there is a gap in content.

        Args:
            location (SourceLocation): The location of the content, in the form
              (lineno, col_offset, end_lineno, end_coloffset).
            pcs (Optional[Set[int]]): The PC values of the statements.
            ws_start (Optional[int]): Optionally provide a white-space starting point
              to back-fill.
        """

        pcs = pcs or set()
        if ws_start is not None and ws_start > location[0]:
            # No new lines.
            return

        function = self.closure
        if not isinstance(function, Function):
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
            content = Content(__root__=new_lines)
            statement = SourceStatement(asts=asts, content=content, pcs=pcs)
            self.statements.append(statement)

        else:
            # Add ASTs to latest statement.
            self.source_statements[-1].asts.extend(asts)
            for pc in pcs:
                self.source_statements[-1].pcs.add(pc)

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
        if not self.source_statements:
            return None

        last_stmt = self.source_statements[-1]
        function = self.closure
        if not isinstance(function, Function):
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
        content = Content(__root__=sorted_dict)
        return SourceStatement(asts=next_stmt_asts, content=content)


class SourceTraceback(BaseModel):
    """
    A full execution traceback including source code.
    """

    __root__: List[ControlFlow]

    @classmethod
    def create(
        cls,
        contract_type: ContractType,
        trace: Iterator[TraceFrame],
        data: Union[HexBytes, str],
    ):
        trace, second_trace = tee(trace)
        if not second_trace or not (accessor := next(second_trace, None)):
            return cls.parse_obj([])

        if not (source_id := contract_type.source_id):
            return cls.parse_obj([])

        ext = f".{source_id.split('.')[-1]}"
        if ext not in accessor.compiler_manager.registered_compilers:
            return cls.parse_obj([])

        compiler = accessor.compiler_manager.registered_compilers[ext]
        try:
            return compiler.trace_source(contract_type, trace, HexBytes(data))
        except NotImplementedError:
            return cls.parse_obj([])

    def __str__(self) -> str:
        return self.format()

    def __repr__(self) -> str:
        return f"<ape.types.SourceTraceback control_paths={len(self.__root__)}>"

    def __len__(self) -> int:
        return len(self.__root__)

    def __iter__(self) -> Iterator[ControlFlow]:  # type: ignore[override]
        yield from self.__root__

    def __getitem__(self, idx: int) -> ControlFlow:
        try:
            return self.__root__[idx]
        except IndexError as err:
            raise IndexError(f"Control flow index '{idx}' out of range.") from err

    def __setitem__(self, key, value):
        return self.__root__.__setitem__(key, value)

    @property
    def revert_type(self) -> Optional[str]:
        """
        The revert type, such as a builtin-error code or a user dev-message,
        if there is one.
        """

        return self.statements[-1].type if self.statements[-1].type != "source" else None

    def append(self, __object) -> None:
        """
        Append the given control flow to this one.
        """
        self.__root__.append(__object)

    def extend(self, __iterable) -> None:
        """
        Append all the control flows from the given traceback to this one.
        """
        if not isinstance(__iterable, SourceTraceback):
            raise TypeError("Can only extend another traceback object.")

        self.__root__.extend(__iterable.__root__)

    @property
    def last(self) -> Optional[ControlFlow]:
        """
        The last control flow in the traceback, if there is one.
        """
        return self.__root__[-1] if len(self.__root__) else None

    @property
    def execution(self) -> List[ControlFlow]:
        """
        All the control flows in order. Each set of statements in
        a control flow is separated by a jump.
        """
        return list(self.__root__)

    @property
    def statements(self) -> List[Statement]:
        """
        All statements from each control flow.
        """
        return list(chain(*[x.statements for x in self.__root__]))

    @property
    def source_statements(self) -> List[SourceStatement]:
        """
        All source statements from each control flow.
        """
        return list(chain(*[x.source_statements for x in self.__root__]))

    def format(self) -> str:
        """
        Get a formatted traceback string for displaying to users.
        """
        if not len(self.__root__):
            # No calls.
            return ""

        header = "Traceback (most recent call last)"
        indent = "  "
        last_depth = None
        segments: List[str] = []
        for control_flow in reversed(self.__root__):
            if last_depth is None or control_flow.depth == last_depth - 1:
                if control_flow.depth == 0 and len(segments) >= 1:
                    # Ignore 0-layer segments if source code was hit
                    continue

                last_depth = control_flow.depth
                content_str = control_flow.format()
                if not content_str.strip():
                    continue

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
                            if not isinstance(function, Function):
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
        self,
        location: SourceLocation,
        function: Function,
        depth: int,
        pcs: Optional[Set[int]] = None,
        source_path: Optional[Path] = None,
    ):
        """
        Add an execution sequence from a jump.

        Args:
            location (``SourceLocation``): The location to add.
            function (``Function``): The function executing.
            source_path (Optional[``Path``]): The path of the source file.
            depth (int): The depth of the function call in the call tree.
            pcs (Optional[Set[int]]): The program counter values.
            source_path (Optional[``Path``]): The path of the source file.
        """

        asts = function.get_content_asts(location)
        content = function.get_content(location)
        if not asts or not content:
            return

        pcs = pcs or set()
        Statement.update_forward_refs()
        ControlFlow.update_forward_refs()
        self._add(asts, content, pcs, function, depth, source_path=source_path)

    def extend_last(self, location: SourceLocation, pcs: Optional[Set[int]] = None):
        """
        Extend the last node with more content.

        Args:
            location (``SourceLocation``): The location of the new content.
            pcs (Optional[Set[int]]): The PC values to add on.
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
        self.last.extend(location, pcs=pcs, ws_start=start)

    def add_builtin_jump(
        self,
        name: str,
        _type: str,
        compiler_name: str,
        full_name: Optional[str] = None,
        source_path: Optional[Path] = None,
        pcs: Optional[Set[int]] = None,
    ):
        """
        A convenience method for appending a control flow that happened
        from an internal compiler built-in code. See the ape-vyper plugin
        for a usage example.

        Args:
            name (str): The name of the compiler built-in.
            _type (str): A str describing the type of check.
            compiler_name (str): The name of the compiler.
            full_name (Optional[str]): A full-name ID.
            source_path (Optional[Path]): The source file related, if there is one.
            pcs (Optional[Set[int]]): Program counter values mapping to this check.
        """
        # TODO: Assess if compiler_name is needed or get rid of in v0.7.
        pcs = pcs or set()
        closure = Closure(name=name, full_name=full_name or name)
        depth = self.last.depth - 1 if self.last else 0
        statement = Statement(type=_type, pcs=pcs)
        flow = ControlFlow(
            closure=closure, depth=depth, statements=[statement], source_path=source_path
        )
        self.append(flow)

    def _add(
        self,
        asts: List[ASTNode],
        content: Content,
        pcs: Set[int],
        function: Function,
        depth: int,
        source_path: Optional[Path] = None,
    ):
        statement = SourceStatement(asts=asts, content=content, pcs=pcs)
        exec_sequence = ControlFlow(
            statements=[statement], source_path=source_path, closure=function, depth=depth
        )
        self.append(exec_sequence)
