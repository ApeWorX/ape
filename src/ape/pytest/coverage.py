from pathlib import Path
from typing import Iterable, List

from ethpm_types.source import ContractSource

from ape.logging import logger
from ape.pytest.config import ConfigWrapper
from ape.types import CoverageReport, SourceTraceback
from ape.types.coverage import CoverageStatement, CoverageProject
from ape.utils import ManagerAccessMixin, get_relative_path, parse_coverage_table


class CoverageData(ManagerAccessMixin):
    def __init__(self, base_path: Path, sources: Iterable[ContractSource]):
        self.base_path = base_path

        # source_id -> pc(s) -> times hit
        self.project_coverage = CoverageProject(name=self.config_manager.name or "__local__")

        for src in sources:
            source_coverage = self.project_coverage.include(source_id)
            contract_coverage = source_coverage.include(src.contract_type.name)

            for pc, item in src.pcmap.__root__.items():
                pc_int = int(pc)
                if pc_int < 0:
                    continue

                loc = item.get("location")
                if not loc and not item.get("dev"):
                    # Not a statement we can measure.
                    continue

                elif loc:
                    loc_tuple = (int(loc[0] or -1), int(loc[2] or -1))
                else:
                    loc_tuple = None

                function = src.lookup_function(loc)
                func_cov = contract_coverage.include(function.name)

                # Check if location already profiled.
                done = False
                for past_stmt in func_cov.statements:
                    if not loc_tuple or (loc_tuple and (past_stmt.location != loc_tuple)):
                        continue

                    # Already tracking this location.
                    past_stmt.pcs.add(pc_int)
                    done = True
                    break

                cov_item = None
                if loc_tuple and not done:
                    # Adding a source-statement for the first time.
                    cov_item = CoverageItem(location=loc_tuple, pcs={pc_int})

                elif not loc_tuple and not done:
                    # Adding a virtual statement.
                    cov_item = CoverageItem(pcs={pc_int})

                if cov_item is not None:
                    statements.append(cov_item)

        # Currently, coverage only supports one project at a time.
        return CoverageReport(projects=[self.project_coverage])


            #
            # # OLD!!!
            # if not src.source_path:
            #     # TODO: Handle source-less files (remote coverage)
            #     continue
            #
            # # Init all valid statements with a zero hit count.

            #
            # source_id = str(get_relative_path(src.source_path.absolute(), base_path.absolute()))
            # self.statements[source_id] = statements

    def cover(self, src_path: Path, pcs: Iterable[int]):
        src_id = str(get_relative_path(src_path.absolute(), self.base_path))
        if src_id not in self.statements:
            # The source is not tracked for coverage.
            return

        handled_pcs = set()
        for pc in pcs:
            if pc < 0:
                continue

            for stmt in self.statements[src_id]:
                if pc in stmt.pcs:
                    stmt.hit_count += 1
                    handled_pcs.add(pc)

        unhandled_pcs = set(pcs) - handled_pcs
        if unhandled_pcs:
            # Maybe a bug in ape.
            logger.debug(f"Unhandled PCs: '{','.join([f'{x}' for x in unhandled_pcs])}'")


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
            if not control_flow.source_path or not control_flow.pcs:
                continue

            self.data.cover(control_flow.source_path, control_flow.pcs)

    def show_session_coverage(self) -> bool:
        if not self.data or not self.data.statements:
            return False

        table = parse_coverage_table(self.data.statements)
        self.chain_manager._reports.echo(table)
        return True
