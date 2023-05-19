from pathlib import Path
from typing import Iterable, Set

from ethpm_types.source import ContractSource, SourceLocation

from ape.logging import logger
from ape.pytest.config import ConfigWrapper
from ape.types import CoverageReport, SourceTraceback
from ape.utils import ManagerAccessMixin, get_relative_path, parse_coverage_table


class CoverageData:
    def __init__(self, base_path: Path, sources: Iterable[ContractSource]):
        self.base_path = base_path

        # source_id -> pc -> times hit
        self.session_coverage_report: CoverageReport = {}

        locations: Set[SourceLocation] = set()

        # Build coverage profile.
        for src in sources:
            if not src.source_path:
                # TODO: Handle source-less files (remote coverage)
                continue

            # Init all relevant PC hits with 0.
            statements = {}
            source_id = str(get_relative_path(src.source_path.absolute(), base_path.absolute()))

            for pc, item in src.pcmap.__root__.items():
                loc = item.get("location")
                if (not loc and not item.get("dev")) or (loc and tuple(loc) in locations):
                    # Not a statement we can measure.
                    continue

                elif loc:
                    # If multiple statements have the exact same location,
                    # only need to track once.
                    # NOTE: Only weird because of mypy.
                    loc_tuple = (
                        int(loc[0] or -1),
                        int(loc[1] or -1),
                        int(loc[2] or -1),
                        int(loc[3] or -1),
                    )
                    locations.add(loc_tuple)

                pc_int = int(pc)
                if pc_int >= 0:
                    statements[pc_int] = 0

            self.session_coverage_report[source_id] = statements

    def cover(self, src_path: Path, pcs: Iterable[int]):
        src_id = str(get_relative_path(src_path.absolute(), self.base_path))
        if src_id not in self.session_coverage_report:
            # Not sure if this is possible, but just in case.
            self.session_coverage_report[src_id] = {}

        for pc in pcs:
            if pc < 0:
                continue
            elif pc in self.session_coverage_report[src_id]:
                self.session_coverage_report[src_id][pc] += 1
            else:
                # Potentially a bug in Ape where we are incorrectly
                # tracking statements.
                logger.debug(f"Found PC not in profile '{pc}'.")


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

            self.data.cover(source_path, control_flow.pcs)

    def show_session_coverage(self) -> bool:
        if not self.data or not self.data.session_coverage_report:
            return False

        table = parse_coverage_table(self.data.session_coverage_report)
        self.chain_manager._reports.echo(table)
        return True
