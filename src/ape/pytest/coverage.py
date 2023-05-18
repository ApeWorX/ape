from typing import Iterable

from ethpm_types.source import ContractSource

from ape.pytest.config import ConfigWrapper
from ape.types import CoverageReport, SourceTraceback
from ape.utils import ManagerAccessMixin, parse_coverage_table


class CoverageData:
    def __init__(self, sources: Iterable[ContractSource]):
        # source_id -> pc -> times hit
        self.session_coverage_report: CoverageReport = {}

        # Build coverage profile.
        for src in sources:
            if not src.source_path:
                # TODO: Handle source-less files (remote coverage)
                continue

            # Init all relevant PC hits with 0.
            pcs = src.pcmap.__root__.items()
            self.session_coverage_report[str(src.source_path)] = {
                int(pc): 0 for pc, x in pcs if x.get("location") or x.get("dev")
            }

    def hit_lines(self, src_id: str, linenos: Iterable[int]):
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
        self.data = CoverageData(sources)

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

            # Build statement hits.
            for statement in control_flow.source_statements:
                linenos = set()
                for no in statement.content.line_numbers:
                    linenos.add(no)

                self.data.hit_lines(str(source_path), linenos)

    def show_session_coverage(self) -> bool:
        if not self.data or not self.data.session_coverage_report:
            return False

        table = parse_coverage_table(self.data.session_coverage_report)
        self.chain_manager._reports.echo(table)
        return True
