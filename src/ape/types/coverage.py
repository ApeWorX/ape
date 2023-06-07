import itertools
from datetime import datetime
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Dict, List, Optional, Set
from xml.dom.minidom import getDOMImplementation
from xml.etree.ElementTree import Element, SubElement, tostring

from ethpm_types import BaseModel
from ethpm_types.source import ContractSource, SourceLocation
from pydantic import validator

from ape.logging import logger
from ape.utils.misc import get_current_timestamp
from ape.version import version as ape_version

_DTD_URL = "https://raw.githubusercontent.com/cobertura/web/master/htdocs/xml/coverage-04.dtd"


class CoverageStatement(BaseModel):
    """
    An item that can get hit during coverage. Examples of coverage items are
    line segments, which are generally calculated from groupings of AST nodes
    occupying the same location, that can be tracked by their PC values. During
    a transaction's trace, we find these values and we find the corresponding
    coverage item and increment the hit count. Another example of a coverage item
    is a compiler-builtin check, also marked by a PC value. If we encounter such
    PC in a trace, its hit count is incremented. Builtin compiler checks may or
    may not correspond to an actual location in the source code, depending on the
    type of check.
    """

    location: Optional[SourceLocation] = None
    """
    The location of the item (line, column, endline, endcolumn).
    If multiple PCs share an exact location, it is only tracked as one.
    """

    pcs: Set[int]
    """
    The PCs for this node.
    """

    hit_count: int = 0
    """
    The times this node was hit.
    """

    tag: Optional[str] = None
    """
    An additional tag to mark this statement with.
    This is useful if the location field is empty.
    """


class FunctionCoverage(BaseModel):
    """
    The individual coverage of a function defined in a smart contact.
    """

    name: str
    """
    The display name of the function.
    """

    full_name: str
    """
    The unique name of the function.
    """

    statements: List[CoverageStatement] = []
    """
    For statement coverage, these are the individual items.
    See :class:`~ape.types.coverage.CoverageStatement` for more details.
    """

    @property
    def lines_covered(self) -> int:
        """
        The number of lines with a hit counter greater than zero in this method.
        """
        return len([x for x in self.statements if x.hit_count > 0])

    @property
    def lines_valid(self) -> int:
        """
        All lines valid for coverage in this method.
        """
        return len(self.statements)

    @property
    def miss_count(self) -> int:
        """
        The number of lines missed.
        """
        return self.lines_valid - self.lines_covered

    @property
    def line_rate(self) -> float:
        """
        The number of lines hit divided by number of lines.
        """
        return self.lines_covered / self.lines_valid if self.lines_valid > 0 else 0

    def dict(self, *args, **kwargs) -> dict:
        attribs = super().dict(*args, **kwargs)

        # Add coverage stats.
        attribs["lines_covered"] = self.lines_covered
        attribs["lines_valid"] = self.lines_valid
        attribs["line_rate"] = self.line_rate

        return attribs

    def profile_statement(
        self, pc: int, location: Optional[SourceLocation] = None, tag: Optional[str] = None
    ):
        """
        Initialize a statement in the coverage profile with a hit count starting at zero.
        This statement is ready to accumlate hits as tests execute.

        Args:
            pc (int): The program counter of the statement.
            location (Optional[ethpm_types.source.SourceStatement]): The location of the statement,
              if it exists.
        """

        for statement in self.statements:
            if not location or (
                location and statement.location and statement.location[0] != location[0]
            ):
                # Starts on a different line.
                continue

            # Already tracking this location.
            statement.pcs.add(pc)

            if not statement.tag:
                statement.tag = tag

            return

        coverage_statement = None
        if location:
            # Adding a source-statement for the first time.
            coverage_statement = CoverageStatement(location=location, pcs={pc}, tag=tag)

        else:
            # Adding a virtual statement.
            coverage_statement = CoverageStatement(pcs={pc}, tag=tag)

        if coverage_statement is not None:
            self.statements.append(coverage_statement)


class ContractCoverage(BaseModel):
    """
    An individual contract's coverage.
    """

    name: str
    """
    The name of the contract.
    """

    functions: List[FunctionCoverage] = []
    """
    The coverage of each function individually.
    """

    @property
    def statements(self) -> List[CoverageStatement]:
        """
        All valid coverage lines from every function in this contract.
        """
        return list(itertools.chain.from_iterable(f.statements for f in self.functions))

    @property
    def lines_covered(self) -> int:
        """
        All lines that have a hit count greater than zero.
        """

        return sum(funcs.lines_covered for funcs in self.functions)

    @property
    def lines_valid(self) -> int:
        """
        The number of lines valid for coverage.
        """
        return len(self.statements)

    @property
    def miss_count(self) -> int:
        """
        The number of lines missed.
        """
        return self.lines_valid - self.lines_covered

    @property
    def line_rate(self) -> float:
        """
        The number of lines hit divided by number of lines.
        """
        return self.lines_covered / self.lines_valid

    @property
    def function_hits(self) -> int:
        """
        The number of functions with a hit counter greater than zero.
        """
        return len([fn for fn in self.functions if fn.lines_covered > 0])

    @property
    def function_rate(self) -> float:
        """
        The rate of functions hit versus total functions.
        """
        return self.function_hits / len(self.functions)

    def __getitem__(self, function_name: str) -> FunctionCoverage:
        func = self.get_function(function_name)
        if func:
            return func

        raise IndexError(f"Function '{function_name}' not found.")

    def dict(self, *args, **kwargs) -> dict:
        attribs = super().dict(*args, **kwargs)

        # Add coverage stats.
        attribs["lines_covered"] = self.lines_covered
        attribs["lines_valid"] = self.lines_valid
        attribs["line_rate"] = self.line_rate

        return attribs

    def include(self, name: str, full_name: str) -> FunctionCoverage:
        # Make sure function is included in coverage.
        func_cov = self.get_function(full_name)
        if func_cov:
            return func_cov

        func_cov = FunctionCoverage(name=name, full_name=full_name)
        self.functions.append(func_cov)
        return func_cov

    def get_function(self, full_name: str) -> Optional[FunctionCoverage]:
        for func in self.functions:
            if func.full_name == full_name:
                return func

        return None


class ContractSourceCoverage(BaseModel):
    """
    An individual source file with coverage collected.
    """

    source_id: str
    """
    The ID of the source covered.
    """

    contracts: List[ContractCoverage] = []
    """
    Coverage for each contract in the source file.
    """

    @property
    def statements(self) -> List[CoverageStatement]:
        """
        All valid coverage lines from every function in every contract in this source.
        """

        return list(itertools.chain.from_iterable(c.statements for c in self.contracts))

    @property
    def lines_covered(self) -> int:
        """
        All lines with a hit count greater than zero from every function
        in every contract in this source.
        """
        return sum(c.lines_covered for c in self.contracts)

    @property
    def lines_valid(self) -> int:
        """
        The number of lines valid for coverage.
        """
        return len(self.statements)

    @property
    def miss_count(self) -> int:
        """
        The number of lines missed.
        """
        return self.lines_valid - self.lines_covered

    @property
    def line_rate(self) -> float:
        """
        The number of lines hit divided by number of lines.
        """
        return self.lines_covered / self.lines_valid if self.lines_valid > 0 else 0

    @property
    def total_functions(self) -> int:
        """
        The total number of functions in this source.
        """
        return sum(len(c.functions) for c in self.contracts)

    @property
    def function_hits(self) -> int:
        """
        The number of functions with a hit counter greater than zero.
        """
        return sum(c.function_hits for c in self.contracts)

    @property
    def function_rate(self) -> float:
        """
        The rate of functions hit versus total functions.
        """
        return self.function_hits / self.total_functions if self.total_functions > 0 else 0

    def dict(self, *args, **kwargs) -> dict:
        attribs = super().dict(*args, **kwargs)

        # Add coverage stats.
        attribs["lines_covered"] = self.lines_covered
        attribs["lines_valid"] = self.lines_valid
        attribs["line_rate"] = self.line_rate

        return attribs

    def include(self, contract_name: str) -> ContractCoverage:
        """
        Ensure a contract is included in the report.
        """

        for contract in self.contracts:
            if contract.name == contract_name:
                return contract

        # Include the contract.
        contract_cov = ContractCoverage(name=contract_name)
        self.contracts.append(contract_cov)
        return contract_cov


class CoverageProject(BaseModel):
    """
    A project with coverage collected.
    """

    name: str
    """
    The name of the project being covered.
    """

    sources: List[ContractSourceCoverage] = []
    """
    Coverage for each source in the project.
    """

    @property
    def statements(self) -> List[CoverageStatement]:
        """
        All valid coverage lines from every function in every contract in every source
        in this project.
        """

        return list(itertools.chain.from_iterable(s.statements for s in self.sources))

    @property
    def lines_covered(self) -> int:
        """
        The number of lines with a hit count greater than zero from every function
        in every contract in every source in this this project.
        """
        return sum(s.lines_covered for s in self.sources)

    @property
    def lines_valid(self) -> int:
        """
        The number of lines valid for coverage.
        """
        return len(self.statements)

    @property
    def miss_count(self) -> int:
        """
        The number of lines missed.
        """
        return self.lines_valid - self.lines_covered

    @property
    def line_rate(self) -> float:
        """
        The number of lines hit divided by number of lines.
        """
        return self.lines_covered / self.lines_valid if self.lines_valid > 0 else 0

    @property
    def total_functions(self) -> int:
        """
        The total number of functions in this source.
        """
        return sum(x.total_functions for x in self.sources)

    @property
    def function_hits(self) -> int:
        """
        The number of functions with a hit counter greater than zero.
        """
        return sum(x.function_hits for x in self.sources)

    @property
    def function_rate(self) -> float:
        """
        The rate of functions hit versus total functions.
        """
        return self.function_hits / self.total_functions if self.total_functions > 0 else 0

    def dict(self, *args, **kwargs) -> dict:
        attribs = super().dict(*args, **kwargs)

        # Add coverage stats.
        attribs["lines_covered"] = self.lines_covered
        attribs["lines_valid"] = self.lines_valid
        attribs["line_rate"] = self.line_rate

        return attribs

    def include(self, contract_source: ContractSource) -> ContractSourceCoverage:
        for src in self.sources:
            if src.source_id == contract_source.source_id:
                return src

        source_cov = ContractSourceCoverage(source_id=contract_source.source_id)
        self.sources.append(source_cov)
        return source_cov


class CoverageReport(BaseModel):
    """
    Coverage report schema inspired from coverage.py.
    """

    timestamp: int
    """
    The timestamp the report was generated.
    """

    projects: List[CoverageProject] = []
    """
    Each project with individual coverage tracked.
    """

    @validator("timestamp", pre=True)
    def validate_timestamp(cls, value):
        # Default to current UTC timestamp.
        return value or int(round(get_current_timestamp()))

    @property
    def sources(self) -> List[str]:
        """
        Every source ID in the report.
        """
        return [s.source_id for p in self.projects for s in p.sources]

    @property
    def statements(self) -> List[CoverageStatement]:
        """
        All valid coverage lines from every function in every contract in every source
        from every project in this report.
        """
        return list(itertools.chain.from_iterable(p.statements for p in self.projects))

    @property
    def lines_covered(self) -> int:
        """
        All lines with a hit count greater than zero from every function
        in every contract in every source in every project in this report.
        """
        return sum(p.lines_covered for p in self.projects)

    @property
    def lines_valid(self) -> int:
        """
        The number of lines valid for coverage.
        """
        return len(self.statements)

    @property
    def miss_count(self) -> int:
        """
        The number of lines missed.
        """
        return self.lines_valid - self.lines_covered

    @property
    def line_rate(self) -> float:
        """
        The number of lines hit divided by number of lines.
        """
        return self.lines_covered / self.lines_valid if self.lines_valid > 0 else 0

    @property
    def total_functions(self) -> int:
        """
        The total number of functions in this source.
        """
        return sum(x.total_functions for x in self.projects)

    @property
    def function_hits(self) -> int:
        """
        The number of functions with a hit counter greater than zero.
        """
        return sum(x.function_hits for x in self.projects)

    @property
    def function_rate(self) -> float:
        """
        The rate of functions hit versus total functions.
        """
        return self.function_hits / self.total_functions if self.total_functions > 0 else 0

    @property
    def xml(self) -> str:
        """
        The coverage XML report as a string.
        """
        xml_out = self._get_xml()
        return xml_out.toprettyxml(indent="  ")

    def _get_xml(self):
        impl = getDOMImplementation()
        if not impl:
            # Only for mypy.
            raise ValueError("Failed to get XML DOM.")

        xml_out = impl.createDocument(None, "coverage", None)

        # NOTE: Some of this is borrowed from coverage.py.

        # Write header.
        xcoverage = xml_out.documentElement
        xcoverage.setAttribute("version", ape_version)
        xcoverage.setAttribute("timestamp", f"{self.timestamp}")
        xcoverage.setAttribute("function-rate", f"{self.function_rate}")
        _add_xml_statement_stats(xcoverage, self)
        xcoverage.appendChild(xml_out.createComment(" Generated by Ape Framework"))
        xcoverage.appendChild(xml_out.createComment(f" Based on  {_DTD_URL} "))

        xprojects = xml_out.createElement("projects")
        for project in self.projects:
            xproject = xml_out.createElement("project")
            xproject.setAttribute("name", project.name)
            xproject.setAttribute("function-rate", f"{project.function_rate}")
            _add_xml_statement_stats(xproject, project)

            xsources = xml_out.createElement("sources")
            for src in project.sources:
                xsource = xml_out.createElement("source")
                xsource.setAttribute("source-id", src.source_id)
                xsource.setAttribute("function-rate", f"{src.function_rate}")
                _add_xml_statement_stats(xsource, src)
                xcontracts = xml_out.createElement("contracts")

                for contract in src.contracts:
                    xcontract = xml_out.createElement("contract")
                    xcontract.setAttribute("name", contract.name)
                    xcontract.setAttribute("function-rate", f"{contract.function_rate}")
                    _add_xml_statement_stats(xcontract, contract)
                    xfunctions = xml_out.createElement("functions")

                    # Use name unless the same function found twice, then use full name.
                    fn_map: Dict[str, FunctionCoverage] = {}
                    singles_used = []
                    for function in contract.functions:
                        singles_used.append(function.name)
                        if (
                            function.name in fn_map
                            and function.full_name != fn_map[function.name].full_name
                        ):
                            # Another method with the same name already in map.
                            # Use full name for both.
                            existing_fn = fn_map[function.name]
                            fn_map[existing_fn.full_name] = existing_fn
                            del fn_map[function.name]
                            fn_map[function.full_name] = function
                        elif function.name in singles_used:
                            # Because this name has already been found once,
                            # we can assume we are using full names for these.
                            fn_map[function.full_name] = function
                        else:
                            # Is first time coming across this name.
                            fn_map[function.name] = function

                    for fn_name, function in fn_map.items():
                        xfunction = xml_out.createElement("function")
                        xfunction.setAttribute("name", fn_name)
                        _add_xml_statement_stats(xfunction, function)
                        xstatements = xml_out.createElement("statements")

                        for statement in function.statements:
                            xstatement = xml_out.createElement("statement")

                            if statement.location:
                                lineno = statement.location[0]
                                end_lineno = statement.location[2]
                                if lineno == end_lineno:
                                    xstatement.setAttribute("line", f"{lineno}")
                                else:
                                    xrange = f"{lineno}-{end_lineno}"
                                    xstatement.setAttribute("lines", xrange)

                            xpcs = ",".join([str(pc) for pc in statement.pcs])
                            xstatement.setAttribute("pcs", xpcs)
                            xstatement.setAttribute("hits", f"{statement.hit_count}")

                            if statement.tag:
                                xstatement.setAttribute("tag", statement.tag)

                            xstatements.appendChild(xstatement)
                        xfunction.appendChild(xstatements)
                        xfunctions.appendChild(xfunction)
                    xcontract.appendChild(xfunctions)
                    xcontracts.appendChild(xcontract)
                xsource.appendChild(xcontracts)
                xsources.appendChild(xsource)
            xproject.appendChild(xsources)
            xprojects.appendChild(xproject)
        xcoverage.appendChild(xprojects)
        return xml_out

    def write_xml(self, path: Path):
        xml = self.xml
        if not xml:
            return

        if path.is_dir():
            path = path / "coverage.xml"

        path.unlink(missing_ok=True)
        path.write_text(xml)

    def write_html(self, path: Path):
        html = self.html
        if not html:
            return

        if path.is_dir():
            # Use as base path if given.
            html_path = path / "htmlcov"
            html_path.mkdir(exist_ok=True)
        elif not path.exists() and path.parent.is_dir():
            # Write to path if given a new one.
            html_path = path
        else:
            raise ValueError("Invalid path argument to `write_html()`.")

        # Create new index.html.
        index = html_path / "index.html"
        index.unlink(missing_ok=True)
        index.write_text(html)

        favicon = html_path / "favicon.ico"
        if not favicon.is_file():
            # Use favicon that already ships with Ape's docs.
            root = Path(__file__).parent
            docs_folder = root / "docs"
            while "ape" in root.as_posix() and not docs_folder.is_dir():
                root = root.parent
                docs_folder = root / "docs"

            docs_favicon = docs_folder / "favicon.ico"
            if docs_folder.is_dir() and docs_favicon.is_file():
                favicon.write_bytes(docs_favicon.read_bytes())
            else:
                # Don't let this stop us from generating the report.
                # Although, this shouldn't happen.
                logger.debug("Failed finding favicon for coverage HTML.")

    @property
    def html(self) -> str:
        """
        The coverage HTML report as a string.
        """
        html = self._get_html()
        html_str = tostring(html, encoding="utf8", method="html").decode()
        return _HTMLPrettfier().prettify(html_str)

    def _get_html(self) -> Any:
        html = Element("html")
        head = SubElement(html, "head")
        meta = SubElement(head, "meta")
        meta.set("http-equiv", "Content-Type")
        meta.set("content", "text/html; charset=utf-8")
        title = SubElement(head, "title")
        title.text = "Contract Coverage Report"
        favicon = SubElement(head, "link")
        favicon.set("rel", "icon")
        favicon.set("sizes", "32x32")
        favicon.set("href", "favicon.ico")
        SubElement(html, "body")
        self._html_header_sub_element(html)
        self._html_main_sub_element(html)
        return html

    def _html_header_sub_element(self, html: Any) -> Any:
        header = SubElement(html, "header")
        div = SubElement(header, "div")
        h1 = SubElement(div, "h1")
        line_rate = round(self.line_rate * 100, 2)
        if str(line_rate).endswith("0"):
            line_rate = int(line_rate)

        h1.text = "Coverage report"

        if len(self.projects) == 1:
            # If only one project, include information here instead of below.
            h1.text += f" for {self.projects[0].name}"

        paragraph = SubElement(div, "p")
        datetime_obj = datetime.fromtimestamp(self.timestamp)
        datetime_string = datetime_obj.strftime("%Y-%m-%d %H:%M:%S")
        paragraph.text = f"Generated by Ape Framework v{ape_version}, {datetime_string}"

    def _html_main_sub_element(self, html: Any):
        main = SubElement(html, "main")
        show_project_header = len(self.projects) > 1
        columns = ("Source", "Statements", "Missing", "Statement Coverage", "Function Coverage")

        for project in self.projects:
            if show_project_header:
                # If only 1 project, it is shown at the top.
                title = SubElement(main, "h2")
                title.text = project.name

            table = SubElement(main, "table")
            thread = SubElement(table, "thread")
            thread_tr = SubElement(thread, "tr")

            for column in columns:
                th = SubElement(thread_tr, "th")
                th.text = column

            tbody = SubElement(table, "tbody")
            tbody_tr = SubElement(tbody, "tr")
            for src in project.sources:
                source_td = SubElement(tbody_tr, "td")
                source_td.text = src.source_id
                stmts_td = SubElement(tbody_tr, "td")
                stmts_td.text = f"{src.lines_valid}"
                missing_td = SubElement(tbody_tr, "td")
                missing_td.text = f"{src.miss_count}"
                stmt_cov_td = SubElement(tbody_tr, "td")
                stmt_cov_td.text = f"{round(src.line_rate * 100, 2)}%"
                fn_cov_td = SubElement(tbody_tr, "td")
                fn_cov_td.text = f"{round(src.function_rate * 100, 2)}%"

    def dict(self, *args, **kwargs) -> dict:
        attribs = super().dict(*args, **kwargs)

        # Add coverage stats.
        attribs["lines_covered"] = self.lines_covered
        attribs["lines_valid"] = self.lines_valid
        attribs["line_rate"] = self.line_rate

        return attribs

    def get_source_coverage(self, source_id: str) -> Optional[ContractSourceCoverage]:
        for project in self.projects:
            for src in project.sources:
                if src.source_id == source_id:
                    return src

        return None


def _add_xml_statement_stats(xobj, cov):
    xobj.setAttribute("lines-valid", f"{cov.lines_valid}")
    xobj.setAttribute("lines-covered", f"{cov.lines_covered}")
    xobj.setAttribute("line-rate", f"{cov.line_rate}")


class _HTMLPrettfier(HTMLParser):
    def __init__(self):
        super().__init__()
        self.no_indent_tags = (
            "html",
            "meta",
        )
        self.no_newline_tags = ("title", "h1", "h2", "th", "td")

        # State variables - get modified during prettification.
        self.indent = 0
        self.prettified_html = "<!DOCTYPE html>\n"

    def prettify(self, html_str: str) -> str:
        """
        This is a custom method not part of the HTMLParser spec
        that ingests a coverage HTML str, handles the formatting, returns it,
        and resets this formatter's instance, so that the operation
        is more functionable.
        """
        self.feed(html_str)
        result = self.prettified_html
        self.reset()
        self.indent = 0
        self.prettified_html = "<!DOCTYPE html>\n"
        return result

    def handle_starttag(self, tag, attrs):
        self.prettified_html += " " * self.indent + "<" + tag
        for attr in attrs:
            self.prettified_html += f' {attr[0]}="{attr[1]}"'

        self.prettified_html += ">"
        if tag not in self.no_newline_tags:
            self.prettified_html += "\n"

        if tag not in self.no_indent_tags:
            self.indent += 2

    def handle_endtag(self, tag):
        self.indent = max(0, self.indent - 2)
        end_tag = f"</{tag}>\n"
        indented = self.prettified_html.endswith("\n")
        content = " " * self.indent + f"</{tag}>\n" if indented else end_tag
        self.prettified_html += content

    def handle_data(self, data):
        data_str = data.strip()
        if not data_str:
            return

        indented = self.prettified_html.endswith("\n")
        content = " " * self.indent + data + "\n" if indented else data
        self.prettified_html += content

    def handle_comment(self, data):
        self.prettified_html += " " * self.indent + f"<!--{data}-->\n"
