from pathlib import Path
from typing import Iterable, Dict, List

from ethpm_types.source import ContractSource
from ethpm_types.utils import SourceLocation

from ape.pytest.config import ConfigWrapper
from ape.types import CoverageReport, SourceTraceback
from ape.utils import ManagerAccessMixin, get_relative_path, parse_coverage_table


class CoverageData:
    def __init__(self, base_path: Path, sources: Iterable[ContractSource]):
        self.base_path = base_path

        # source_id -> pc -> times hit
        self.session_coverage_report: CoverageReport = {}

        # Build coverage profile.
        for src in sources:
            if not src.source_path:
                # TODO: Handle source-less files (remote coverage)
                continue

            # Init all relevant PC hits with 0.
            pcs: List[Dict] = list(src.pcmap.__root__.values())
            source_id = str(get_relative_path(src.source_path.absolute(), base_path.absolute()))
            statements = {}
            for pc_item in pcs:
                if not pc_item.get("location"):
                    continue

                loc: SourceLocation = pc_item["location"]
                for no in range(loc[0], loc[2] + 1):
                    statements[int(no)] = 0

            self.session_coverage_report[source_id] = statements

    def hit_lines(self, src_path: Path, linenos: Iterable[int]):
        src_id = str(get_relative_path(src_path.absolute(), self.base_path))
        if src_id not in self.session_coverage_report:
            # Not sure if this is possible, but just in case.
            self.session_coverage_report[src_id] = {}

        for no in linenos:
            if no in self.session_coverage_report[src_id]:
                self.session_coverage_report[src_id][no] += 1
            else:
                self.session_coverage_report[src_id][no] = 1


class CoverageTracker(ManagerAccessMixin):
    def __init__(self, config_wrapper: ConfigWrapper):
        self.config_wrapper = config_wrapper
        sources = self.project_manager._contract_sources
        self.data = CoverageData(self.project_manager.contracts_folder, sources)

    @property
    def enabled(self) -> bool:
        return self.config_wrapper.track_coverage

    def cover(self, traceback: SourceTraceback):
        """
        Track the coverage from the given source traceback.

        Args:
            traceback (:class:`~ape.types.trace.SourceTraceback`):
              The class instance containing all the information regarding
              sources covered for a particular transaction.
        """
        for control_flow in traceback:
            source_path = control_flow.source_path
            if not source_path:
                continue

            # Build statement hits.
            for statement in control_flow.source_statements:
                linenos = set()
                for no in statement.content.line_numbers:
                    linenos.add(no)

                self.data.hit_lines(source_path, linenos)

    def show_session_coverage(self) -> bool:
        if not self.data or not self.data.session_coverage_report:
            return False

        table = parse_coverage_table(self.data.session_coverage_report)
        self.chain_manager._reports.echo(table)
        return True
