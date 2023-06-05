from typing import List, Optional, Set, Tuple
from xml.dom.minidom import getDOMImplementation

from ethpm_types import BaseModel
from ethpm_types.source import SourceLocation
from pydantic import validator

from ape.utils.misc import get_current_timestamp
from ape.version import version as ape_version

_DTD_URL = "https://raw.githubusercontent.com/cobertura/web/master/htdocs/xml/coverage-04.dtd"


class CoverageStatement(BaseModel):
    """
    An item that can get hit during coverage. Examples of coverage items are
    line segments, which are generally calculated from groupings of AST occupying
    the same location, that can be tracked by their PC values. During a transaction's
    trace, we find these values and we find the corresponding coverage item and
    increment the hit count. Another example of a coverage item is a compiler-builtin
    check, also marked by a PC value. If we encounter such PC in a trace, its hit
    count is incremented. Builtin compiler checks may or may not correspond to an
    actual location in the source code, depending on the type of check.
    """

    location: Optional[Tuple[int, int]] = None
    """
    The location of the item (line start to line end). If multiple PCs share an exact location,
    it is only tracked as one.
    """

    pcs: Set[int]
    """
    The PCs for this node.
    """

    hit_count: int = 0
    """
    The times this node was hit.
    """


class FunctionCoverage(BaseModel):
    """
    The individual coverage of a function defined in a smart contact.
    """

    name: str
    """
    The name of the function.
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
        return self.lines_covered / self.lines_valid

    def dict(self, *args, **kwargs) -> dict:
        attribs = super().dict(*args, **kwargs)

        # Add coverage stats.
        attribs["lines_covered"] = self.lines_covered
        attribs["lines_valid"] = self.lines_valid
        attribs["line_rate"] = self.line_rate

        return attribs

    def profile_statement(self, pc: int, location: Optional[SourceLocation] = None):
        """
        Initialize a statement in the coverage profile with a hit count starting at zero.
        This statement is ready to accumlate hits as tests execute.

        Args:
            pc (int): The program counter of the statement.
            location (Optional[ethpm_types.source.SourceStatement]): The location of the statement,
              if it exists.
        """

        line_nos = (int(location[0] or -1), int(location[2] or -1)) if location else None
        done = False
        for statement in self.statements:
            if not line_nos or (line_nos and (statement.location != line_nos)):
                continue

            # Already tracking this location.
            statement.pcs.add(pc)
            done = True
            break

        coverage_statement = None
        if line_nos and not done:
            # Adding a source-statement for the first time.
            coverage_statement = CoverageStatement(location=line_nos, pcs={pc})

        elif not line_nos and not done:
            # Adding a virtual statement.
            coverage_statement = CoverageStatement(pcs={pc})

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
    def lines(self) -> List[CoverageStatement]:
        """
        All valid coverage lines from every function in this contract.
        """

        statements = []
        for funcs in self.functions:
            statements.extend(funcs.statements)

        return statements

    @property
    def lines_covered(self) -> int:
        """
        All lines that have a hit count greater than zero.
        """

        count = 0
        for funcs in self.functions:
            count += funcs.lines_covered

        return count

    @property
    def lines_valid(self) -> int:
        """
        The number of lines valid for coverage.
        """
        return len(self.lines)

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

    def include(self, function_name: str) -> FunctionCoverage:
        # Make sure function is included in coverage.
        func_cov = self.get_function(function_name)
        if func_cov:
            return func_cov

        func_cov = FunctionCoverage(name=function_name)
        self.functions.append(func_cov)
        return func_cov

    def get_function(self, name: str) -> Optional[FunctionCoverage]:
        for func in self.functions:
            if func.name == name:
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

        statements = []
        for contract in self.contracts:
            statements.extend(contract.lines)

        return statements

    @property
    def lines_covered(self) -> int:
        """
        All lines with a hit count greater than zero from every function
        in every contract in this source.
        """

        count = 0
        for contract in self.contracts:
            count += contract.lines_covered

        return count

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
    def function_rate(self) -> float:
        """
        The rate of functions hit versus total functions.
        """
        total = sum([len(c.functions) for c in self.contracts])
        total_hits = sum([c.function_hits for c in self.contracts])
        return total_hits / total

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
    def lines(self) -> List[CoverageStatement]:
        """
        All valid coverage lines from every function in every contract in every source
        in this project.
        """

        statements = []
        for src in self.sources:
            statements.extend(src.statements)

        return statements

    @property
    def lines_covered(self) -> int:
        """
        The number of lines with a hit count greater than zero from every function
        in every contract in every source in this this project.
        """

        count = 0
        for src in self.sources:
            count += src.lines_covered

        return count

    @property
    def lines_valid(self) -> int:
        """
        The number of lines valid for coverage.
        """
        return len(self.lines)

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

    def dict(self, *args, **kwargs) -> dict:
        attribs = super().dict(*args, **kwargs)

        # Add coverage stats.
        attribs["lines_covered"] = self.lines_covered
        attribs["lines_valid"] = self.lines_valid
        attribs["line_rate"] = self.line_rate

        return attribs

    def include(self, source_id: str) -> ContractSourceCoverage:
        for src in self.sources:
            if src.source_id == source_id:
                return src

        # Make sure is included.
        source_cov = ContractSourceCoverage(source_id=source_id)
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
    def lines(self) -> List[CoverageStatement]:
        """
        All valid coverage lines from every function in every contract in every source
        from every project in this report.
        """

        statements = []
        for project in self.projects:
            statements.extend(project.lines)

        return statements

    @property
    def lines_covered(self) -> int:
        """
        All lines with a hit count greater than zero from every function
        in every contract in every source in this this project.
        """

        count = 0
        for project in self.projects:
            count += project.lines_covered

        return count

    @property
    def lines_valid(self) -> int:
        """
        The number of lines valid for coverage.
        """
        return len(self.lines)

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
    def xml(self) -> str:
        impl = getDOMImplementation()
        if not impl:
            raise ValueError("Failed to get XML DOM.")

        xml_out = impl.createDocument(None, "coverage", None)

        # NOTE: Some of this is borrowed from coverage.py.

        # Write header.
        xcoverage = xml_out.documentElement
        xcoverage.setAttribute("version", ape_version)
        xcoverage.setAttribute("timestamp", f"{self.timestamp}")
        _add_xml_stats(xcoverage, self)
        xcoverage.appendChild(xml_out.createComment(" Generated by Ape Framework"))
        xcoverage.appendChild(xml_out.createComment(f" Based on  {_DTD_URL} "))

        xprojects = xml_out.createElement("projects")
        for project in self.projects:
            xproject = xml_out.createElement("project")
            xproject.setAttribute("name", project.name)
            _add_xml_stats(xproject, project)

            xsources = xml_out.createElement("sources")
            for src in project.sources:
                xsource = xml_out.createElement("source")
                xsource.setAttribute("source-id", src.source_id)
                _add_xml_stats(xsource, src)
                xcontracts = xml_out.createElement("contracts")

                for contract in src.contracts:
                    xcontract = xml_out.createElement("contract")
                    xcontract.setAttribute("name", contract.name)
                    _add_xml_stats(xcontract, contract)
                    xfunctions = xml_out.createElement("functions")

                    for function in contract.functions:
                        xfunction = xml_out.createElement("function")
                        xfunction.setAttribute("name", function.name)
                        _add_xml_stats(xfunction, function)
                        xstatements = xml_out.createElement("statements")

                        for statement in function.statements:
                            xstatement = xml_out.createElement("statement")

                            if statement.location:
                                xrange = f"{statement.location[0]}-{statement.location[1]}"
                                xstatement.setAttribute("linenos", xrange)

                            xpcs = ",".join([str(pc) for pc in statement.pcs])
                            xstatement.setAttribute("pcs", xpcs)
                            xstatement.setAttribute("hits", f"{statement.hit_count}")
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

        return xml_out.toprettyxml()

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


def _add_xml_stats(xobj, cov):
    xobj.setAttribute("lines-valid", f"{cov.lines_valid}")
    xobj.setAttribute("lines-covered", f"{cov.lines_covered}")
    xobj.setAttribute("line-rate", f"{cov.line_rate}")
