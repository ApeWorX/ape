import itertools
from datetime import datetime
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Optional
from xml.dom.minidom import getDOMImplementation
from xml.etree.ElementTree import Element, SubElement, tostring

import requests
from ethpm_types.source import ContractSource, SourceLocation
from pydantic import NonNegativeInt, field_validator

from ape.logging import logger
from ape.utils.basemodel import BaseModel
from ape.utils.misc import get_current_timestamp_ms
from ape.version import version as ape_version

_APE_DOCS_URL = "https://docs.apeworx.io/ape/stable/index.html"
_DTD_URL = "https://raw.githubusercontent.com/cobertura/web/master/htdocs/xml/coverage-04.dtd"
_CSS = """
@import url("https://fonts.cdnfonts.com/css/barlow");

html {
  font-weight: 400;
  font-family: "Barlow", sans-serif;
  min-height: 100%;
  background: #8DCAEF;
  font-size: 17px;
}

body {
  font-weight: 400;
  font-family: "Barlow", sans-serif;
  min-height: 100%;
  font-size: 17px;
}

p {
  font-weight: 400;
  font-family: "Barlow", sans-serif;
  font-size: 18px;
  text-align: center;
  padding-bottom: 10px;
}

h1 {
  font-size: 60px;
  line-height: 54px;
  font-weight: 600;
  font-family: "Barlow", sans-serif;
  text-transform: uppercase;
  letter-spacing: -0.05em;
  color: #29B285;
  padding: 0 !important;
  text-align: center;
}

h2 {
  font-size: 30px;
  line-height: 27px;
  font-weight: 600;
  font-family: "Barlow", sans-serif;
  text-transform: uppercase;
  letter-spacing: -0.05em;
  color: #29B285;
  padding: 0 !important;
  display: flex;
  justify-content: space-between;
}

.left-aligned {
  text-align: left;
}

.right-aligned {
  text-align: right;
}

.table-center {
  width: 60%;
  margin: 0 auto;
  padding-left: 10%;
  padding-right: 10%;
}

table {
  width: 80%;
  margin: 0 auto;
  padding-left: 10%;
  padding-right: 10%;
  padding-bottom: 64px;
}

th,
td {
  padding: 8px;
}

th.column1,
td.column1 {
  text-align: left;
}

th.column2,
td.column2,
th.column3,
td.column3,
th.column4,
td.column4,
th.column5,
td.column5 {
  text-align: right;
}
""".lstrip()


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

    pcs: set[int]
    """
    The PCs for this node.
    """

    hit_count: NonNegativeInt = 0
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

    statements: list[CoverageStatement] = []
    """
    For statement coverage, these are the individual items.
    See :class:`~ape.types.coverage.CoverageStatement` for more details.
    """

    hit_count: NonNegativeInt = 0
    """
    The times this function was called.
    **NOTE**: This is needed as a separate data point since not all methods may have
    statements (such as auto-getters).
    """

    @property
    def lines_covered(self) -> NonNegativeInt:
        """
        The number of lines with a hit counter greater than zero in this method.
        """
        return len([x for x in self.statements if x.hit_count > 0])

    @property
    def lines_valid(self) -> NonNegativeInt:
        """
        All lines valid for coverage in this method.
        """
        return len(self.statements)

    @property
    def miss_count(self) -> NonNegativeInt:
        """
        The number of lines missed.
        """
        return self.lines_valid - self.lines_covered

    @property
    def line_rate(self) -> float:
        """
        The number of lines hit divided by number of lines.
        """
        if not self.statements:
            # If there are no statements, rely on fn hit count only.
            return 1.0 if self.hit_count > 0 else 0.0

        # This function has hittable statements.
        return self.lines_covered / self.lines_valid if self.lines_valid > 0 else 0

    def model_dump(self, *args, **kwargs) -> dict:
        attribs = super().model_dump(*args, **kwargs)

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
        This statement is ready to accumulate hits as tests execute.

        Args:
            pc (int): The program counter of the statement.
            location (Optional[ethpm_types.source.SourceStatement]): The location of the statement,
              if it exists.
            tag (Optional[str]): Optionally provide more information about the statements being hit.
              This is useful for builtin statements that may be missing context otherwise.
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

    functions: list[FunctionCoverage] = []
    """
    The coverage of each function individually.
    """

    @property
    def statements(self) -> list[CoverageStatement]:
        """
        All valid coverage lines from every function in this contract.
        """
        return list(itertools.chain.from_iterable(f.statements for f in self.functions))

    @property
    def lines_covered(self) -> NonNegativeInt:
        """
        All lines that have a hit count greater than zero.
        """

        return sum(funcs.lines_covered for funcs in self.functions)

    @property
    def lines_valid(self) -> NonNegativeInt:
        """
        The number of lines valid for coverage.
        """
        return len(self.statements)

    @property
    def miss_count(self) -> NonNegativeInt:
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
    def function_hits(self) -> NonNegativeInt:
        """
        The number of functions with a hit counter greater than zero.
        """
        return len([fn for fn in self.functions if fn.hit_count > 0])

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

        raise KeyError(f"Function '{function_name}' not found.")

    def model_dump(self, *args, **kwargs) -> dict:
        attribs = super().model_dump(*args, **kwargs)

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

    contracts: list[ContractCoverage] = []
    """
    Coverage for each contract in the source file.
    """

    @property
    def statements(self) -> list[CoverageStatement]:
        """
        All valid coverage lines from every function in every contract in this source.
        """

        return list(itertools.chain.from_iterable(c.statements for c in self.contracts))

    @property
    def lines_covered(self) -> NonNegativeInt:
        """
        All lines with a hit count greater than zero from every function
        in every contract in this source.
        """
        return sum(c.lines_covered for c in self.contracts)

    @property
    def lines_valid(self) -> NonNegativeInt:
        """
        The number of lines valid for coverage.
        """
        return len(self.statements)

    @property
    def miss_count(self) -> NonNegativeInt:
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
    def total_functions(self) -> NonNegativeInt:
        """
        The total number of functions in this source.
        """
        return sum(len(c.functions) for c in self.contracts)

    @property
    def function_hits(self) -> NonNegativeInt:
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

    def model_dump(self, *args, **kwargs) -> dict:
        attribs = super().model_dump(*args, **kwargs)

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

    sources: list[ContractSourceCoverage] = []
    """
    Coverage for each source in the project.
    """

    @property
    def statements(self) -> list[CoverageStatement]:
        """
        All valid coverage lines from every function in every contract in every source
        in this project.
        """

        return list(itertools.chain.from_iterable(s.statements for s in self.sources))

    @property
    def lines_covered(self) -> NonNegativeInt:
        """
        The number of lines with a hit count greater than zero from every function
        in every contract in every source in this this project.
        """
        return sum(s.lines_covered for s in self.sources)

    @property
    def lines_valid(self) -> NonNegativeInt:
        """
        The number of lines valid for coverage.
        """
        return len(self.statements)

    @property
    def miss_count(self) -> NonNegativeInt:
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
    def total_functions(self) -> NonNegativeInt:
        """
        The total number of functions in this source.
        """
        return sum(x.total_functions for x in self.sources)

    @property
    def function_hits(self) -> NonNegativeInt:
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

    def model_dump(self, *args, **kwargs) -> dict:
        attribs = super().model_dump(*args, **kwargs)

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

    source_folders: list[Path]
    """
    All source folders to use. This is needed for codecov.
    """

    timestamp: int
    """
    The timestamp the report was generated, in milliseconds.
    """

    projects: list[CoverageProject] = []
    """
    Each project with individual coverage tracked.
    """

    @field_validator("timestamp", mode="before")
    @classmethod
    def validate_timestamp(cls, value):
        # Default to current UTC timestamp (ms).
        return value or get_current_timestamp_ms()

    @property
    def sources(self) -> list[str]:
        """
        Every source ID in the report.
        """
        return [s.source_id for p in self.projects for s in p.sources]

    @property
    def statements(self) -> list[CoverageStatement]:
        """
        All valid coverage lines from every function in every contract in every source
        from every project in this report.
        """
        return list(itertools.chain.from_iterable(p.statements for p in self.projects))

    @property
    def lines_covered(self) -> NonNegativeInt:
        """
        All lines with a hit count greater than zero from every function
        in every contract in every source in every project in this report.
        """
        return sum(p.lines_covered for p in self.projects)

    @property
    def lines_valid(self) -> NonNegativeInt:
        """
        The number of lines valid for coverage.
        """
        return len(self.statements)

    @property
    def miss_count(self) -> NonNegativeInt:
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
    def total_functions(self) -> NonNegativeInt:
        """
        The total number of functions in this source.
        """
        return sum(x.total_functions for x in self.projects)

    @property
    def function_hits(self) -> NonNegativeInt:
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

    def get_xml(self) -> str:
        """
        The coverage XML report as a string. The XML coverage data schema is
        meant to be compatible with codecov.io. Thus, some of coverage is modified
        slightly, and some of the naming conventions (based on 90s Java) won't be
        super relevant to smart-contract projects.
        """
        # See _DTD_URL to learn more about the schema.
        xml_out = self._get_xml()
        return xml_out.toprettyxml(indent="  ")

    def _get_xml(self):
        # NOTE: Some of this implementation is borrowed from coverage.py.
        impl = getDOMImplementation()
        if not impl:
            # Only for mypy.
            raise ValueError("Failed to get XML DOM.")

        xml_out = impl.createDocument(None, "coverage", None)
        xcoverage = xml_out.documentElement

        # Unable to use too exotic of a version.
        xversion = ape_version.split(".dev")[0].strip()
        xcoverage.setAttribute("version", xversion)

        # Add top-level statement stats.
        xcoverage.setAttribute("timestamp", f"{self.timestamp}")
        xcoverage.setAttribute("lines-valid", f"{self.lines_valid}")
        xcoverage.setAttribute("lines-covered", f"{self.lines_covered}")
        xcoverage.setAttribute("line-rate", f"{round(self.line_rate, 4)}")

        # NOTE: Branch fields are required in the schema.
        # TODO: Replace with actual branch coverage when exists.
        xcoverage.setAttribute("branches-covered", "0")
        xcoverage.setAttribute("branches-valid", "0")
        xcoverage.setAttribute("branch-rate", "0")

        # I don't know what this, but it is also required.
        xcoverage.setAttribute("complexity", "0")

        # Add comments.
        xcoverage.appendChild(
            xml_out.createComment(f" Generated by Ape Framework: {_APE_DOCS_URL}")
        )
        xcoverage.appendChild(xml_out.createComment(f" Based on  {_DTD_URL} "))

        # In the XML schema, sources refer to root directories containing source code.
        # In our case, that would typically be the "contracts" folder of the project.
        # NOTE: This is critical and necessary for codecov to map sources correctly.
        xsources = xml_out.createElement("sources")
        for source_path in self.source_folders:
            xsource = xml_out.createElement("source")
            xtxt = xml_out.createTextNode(source_path.as_posix())
            xsource.appendChild(xtxt)
            xsources.appendChild(xsource)

        xcoverage.appendChild(xsources)

        # projects = packages.
        xpackages = xml_out.createElement("packages")
        for project in self.projects:
            xpackage = xml_out.createElement("package")

            # NOTE: For now, always use "." as the package name.
            # TODO: Experiment with using `self.project.name` as package name.
            # If it is "__local__", definitely use "." instead here.
            xpackage.setAttribute("name", ".")

            # Add package-level stats.
            xpackage.setAttribute("line-rate", f"{round(project.line_rate, 4)}")
            xpackage.setAttribute("branch-rate", "0")  # TODO
            xpackage.setAttribute("complexity", "0")

            # The `classes` field refers to `contracts` in our case.
            xclasses = xml_out.createElement("classes")
            for src in project.sources:
                for contract in src.contracts:
                    xclass = xml_out.createElement("class")
                    xclass.setAttribute("name", src.source_id)
                    xclass.setAttribute("line-rate", f"{round(contract.line_rate, 4)}")
                    xclass.setAttribute("branch-rate", "0")  # TODO
                    xclass.setAttribute("complexity", "0")

                    # NOTE: I am not sure what this does or why it is needed.
                    # Also, I am not sure why we don't map statements to the methods.
                    # because we totally could do that. Nonetheless, we have to follow
                    # the schema.
                    xml_out.createElement("methods")

                    # Use name unless the same function found twice, then use full name.
                    fn_map: dict[str, FunctionCoverage] = {}
                    fn_singles_used = []

                    # For the XML report, we split all statements to be only 1 line long.
                    # Each class (contract) can only identify the statement (line number) once.
                    lines_to_add: dict[int, int] = {}
                    xlines = xml_out.createElement("lines")

                    for function in contract.functions:
                        fn_singles_used.append(function.name)
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
                        elif function.name in fn_singles_used:
                            # Because this name has already been found once,
                            # we can assume we are using full names for these.
                            fn_map[function.full_name] = function
                        else:
                            # Is first time coming across this name.
                            fn_map[function.name] = function

                    for fn_name, function in fn_map.items():
                        if not function.statements or not any(
                            s.location for s in function.statements
                        ):
                            # Functions without source-locatable statements are not
                            # permitted in the XML report. This mean auto-getter hits
                            # won't be included as well as any builtin lines. Use other
                            # reportsF to find that level of information.
                            continue

                        for statement in function.statements:
                            if not statement.location:
                                # Statements without line numbers are excluded from this report.
                                # That level of granularity is present in other reports however.
                                # The XML report is strict so it can merge with others.
                                continue

                            for lineno in range(statement.location[0], statement.location[2] + 1):
                                if lineno in lines_to_add:
                                    lines_to_add[lineno] += statement.hit_count
                                else:
                                    lines_to_add[lineno] = statement.hit_count

                    # NOTE: Line numbers must be sorted in the XML!
                    sorted_nos = sorted(list(lines_to_add.keys()))
                    for no in sorted_nos:
                        hits = lines_to_add[no]
                        xline = xml_out.createElement("line")
                        xline.setAttribute("number", f"{no}")
                        xline.setAttribute("hits", f"{hits}")

                        xlines.appendChild(xline)
                        xclass.appendChild(xlines)
                    xclass.appendChild(xlines)
                    xclasses.appendChild(xclass)
            xpackage.appendChild(xclasses)
            xpackages.appendChild(xpackage)
        xcoverage.appendChild(xpackages)
        return xml_out

    def write_xml(self, path: Path):
        if not (xml := self.get_xml()):
            return

        elif path.is_dir():
            path = path / "coverage.xml"

        path.unlink(missing_ok=True)
        path.write_text(xml, encoding="utf8")

    def write_html(self, path: Path, verbose: bool = False):
        if not (html := self.get_html(verbose=verbose)):
            return

        elif path.is_dir():
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
        index.write_text(html, encoding="utf8")

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
                # Try downloading from the internet. This may happen if running
                # ape in an isolated file system or a temporary directory,
                # such as CI/CD tests for Ape.
                try:
                    url = "https://github.com/ApeWorX/ape/blob/main/docs/favicon.ico"
                    response = requests.get(url)
                    response.raise_for_status()  # Check for any errors during the request
                    favicon.write_bytes(response.content)
                except Exception as err:
                    # Don't let this stop us from generating the report.
                    logger.debug(f"Failed finding favicon for coverage HTML. {err}")

            css = html_path / "styles.css"
            css.unlink(missing_ok=True)
            css.write_text(_CSS, encoding="utf8")

    def get_html(self, verbose: bool = False) -> str:
        """
        The coverage HTML report as a string.
        """
        html = self._get_html(verbose=verbose)
        html_str = tostring(html, encoding="utf8", method="html").decode()
        return _HTMLPrettfier().prettify(html_str)

    def _get_html(self, verbose: bool = False) -> Any:
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
        css = SubElement(head, "link")
        css.set("rel", "stylesheet")
        css.set("href", "styles.css")
        SubElement(html, "body")
        self._html_header_sub_element(html)
        self._html_main_sub_element(html, verbose=verbose)
        return html

    def _html_header_sub_element(self, html: Any) -> Any:
        header = SubElement(html, "header")
        div = SubElement(header, "div")
        h1 = SubElement(div, "h1")
        h1.text = "Coverage report"

        if len(self.projects) == 1:
            # If only one project, include information here instead of below.
            h1.text += f" for {self.projects[0].name}"

        paragraph = SubElement(div, "p")
        datetime_obj = datetime.fromtimestamp(self.timestamp / 1000)
        datetime_string = datetime_obj.strftime("%Y-%m-%d %H:%M:%S")
        paragraph.text = f"Generated by Ape Framework v{ape_version}, {datetime_string}"

    def _html_main_sub_element(self, html: Any, verbose: bool = False):
        main = SubElement(html, "main")
        show_project_header = len(self.projects) > 1
        if verbose:
            self._html_main_verbose_sub_element(main, show_project_header=show_project_header)
        else:
            self._html_main_non_verbose_sub_element(main, show_project_header=show_project_header)

    def _html_main_non_verbose_sub_element(self, main: Any, show_project_header: bool = True):
        columns = ("Source", "Statements", "Missing", "Statement Coverage", "Function Coverage")

        for project in self.projects:
            if show_project_header:
                # If only 1 project, it is shown at the top.
                title = SubElement(main, "h2")
                title.text = project.name

            table = SubElement(main, "table", {})
            thread = SubElement(table, "thread")
            thread_tr = SubElement(thread, "tr")

            for idx, column in enumerate(columns):
                th = SubElement(thread_tr, "th", {}, **{"class": f"column{idx + 1}"})
                th.text = column

            tbody = SubElement(table, "tbody")
            for src in project.sources:
                tbody_tr = SubElement(tbody, "tr")
                source_td = SubElement(tbody_tr, "td", {}, **{"class": "column1"})
                source_td.text = src.source_id
                self._set_common_td(tbody_tr, src)
                fn_cov_td = SubElement(tbody_tr, "td", {}, **{"class": "column5"})
                fn_cov_td.text = f"{round(src.function_rate * 100, 2)}%"

    def _html_main_verbose_sub_element(self, main: Any, show_project_header: bool = True):
        columns = (
            "Source",
            "Statements",
            "Missing",
            "Statement Coverage",
        )

        for project in self.projects:
            if show_project_header:
                # If only 1 project, it is shown at the top.
                title = SubElement(main, "h2")
                title.text = str(project.name)
                src_type = "h3"
            else:
                src_type = "h2"

            for src in project.sources:
                table_header_h = SubElement(main, src_type, {}, **{"class": "table-center"})
                stmt_cov = f"{round(src.line_rate * 100, 2)}%"
                fn_cov = f"{round(src.function_rate * 100, 2)}%"
                left_span = SubElement(table_header_h, "span", {}, **{"class": "left-aligned"})
                left_span.text = src.source_id
                right_span = SubElement(table_header_h, "span", {}, **{"class": "right-aligned"})
                right_span.text = f"stmt={stmt_cov} function={fn_cov}"
                table = SubElement(main, "table")
                thread = SubElement(table, "thread")
                thread_tr = SubElement(thread, "tr")

                for idx, column in enumerate(columns):
                    th = SubElement(thread_tr, "th", {}, **{"class": f"column{idx + 1}"})
                    th.text = column

                tbody = SubElement(table, "tbody")

                for contract in src.contracts:
                    for function in contract.functions:
                        tbody_tr = SubElement(tbody, "tr")
                        function_td = SubElement(tbody_tr, "td", {}, **{"class": "column1"})

                        # NOTE: Use the full name if the short name is repeated.
                        function_td.text = (
                            function.full_name
                            if len([fn for fn in contract.functions if fn.name == function.name])
                            > 1
                            else function.name
                        )

                        self._set_common_td(tbody_tr, function)

    def _set_common_td(self, tbody_tr: Any, src_or_fn: Any):
        stmts_td = SubElement(tbody_tr, "td", {}, **{"class": "column2"})
        stmts_td.text = f"{src_or_fn.lines_valid}"
        missing_td = SubElement(tbody_tr, "td", {}, **{"class": "column3"})
        missing_td.text = f"{src_or_fn.miss_count}"
        stmt_cov_td = SubElement(tbody_tr, "td", {}, **{"class": "column4"})
        stmt_cov_td.text = f"{round(src_or_fn.line_rate * 100, 2)}%"

    def model_dump(self, *args, **kwargs) -> dict:
        attribs = super().model_dump(*args, **kwargs)

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
