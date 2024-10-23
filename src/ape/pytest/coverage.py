from collections.abc import Iterable
from pathlib import Path
from typing import Callable, Optional, Union

import click
from ethpm_types.abi import MethodABI
from ethpm_types.source import ContractSource

from ape.logging import logger
from ape.managers.project import ProjectManager
from ape.pytest.config import ConfigWrapper
from ape.types.coverage import CoverageProject, CoverageReport
from ape.types.trace import ContractFunctionPath, ControlFlow, SourceTraceback
from ape.utils.basemodel import ManagerAccessMixin
from ape.utils.misc import get_current_timestamp_ms
from ape.utils.os import get_full_extension, get_relative_path
from ape.utils.trace import parse_coverage_tables


class CoverageData(ManagerAccessMixin):
    def __init__(
        self,
        project: ProjectManager,
        sources: Union[Iterable[ContractSource], Callable[[], Iterable[ContractSource]]],
    ):
        self.project = project
        self._sources: Union[Iterable[ContractSource], Callable[[], Iterable[ContractSource]]] = (
            sources
        )
        self._report: Optional[CoverageReport] = None

    @property
    def sources(self) -> list[ContractSource]:
        if isinstance(self._sources, list):
            return self._sources

        elif callable(self._sources):
            # Lazily evaluated.
            self._sources = self._sources()

        self._sources = [src for src in self._sources]
        return self._sources

    @property
    def report(self) -> CoverageReport:
        if self._report is None:
            self._report = self._init_coverage_profile()

        return self._report

    def reset(self):
        self._report = None
        self._init_coverage_profile()

    def _init_coverage_profile(
        self,
    ) -> CoverageReport:
        # source_id -> pc(s) -> times hit
        project_coverage = CoverageProject(name=self.project.name or "__local__")

        for src in self.sources:
            source_cov = project_coverage.include(src)
            ext = get_full_extension(Path(src.source_id))
            if ext not in self.compiler_manager.registered_compilers:
                continue

            compiler = self.compiler_manager.registered_compilers[ext]
            try:
                compiler.init_coverage_profile(source_cov, src)
            except NotImplementedError:
                continue

        timestamp = get_current_timestamp_ms()
        report = CoverageReport(
            projects=[project_coverage],
            source_folders=[self.project.contracts_folder],
            timestamp=timestamp,
        )

        # Remove empties.
        for project in report.projects:
            project.sources = [x for x in project.sources if len(x.statements) > 0]

        return report

    def cover(
        self, src_path: Path, pcs: Iterable[int], inc_fn_hits: bool = True
    ) -> tuple[set[int], list[str]]:
        if hasattr(self.project, "path"):
            source_id = str(get_relative_path(src_path.absolute(), self.project.path))
        else:
            source_id = str(src_path)

        if source_id not in self.report.sources:
            # The source is not tracked for coverage.
            return set(), []

        handled_pcs = set()
        functions_incremented: list[str] = []
        for pc in pcs:
            if pc < 0:
                continue

            if not (source_coverage := self.report.get_source_coverage(source_id)):
                continue

            for contract in source_coverage.contracts:
                for function in contract.functions:
                    statements_hit = []
                    for statement in function.statements:
                        if statement in statements_hit or pc not in statement.pcs:
                            # With 1 group of PCs, can only hit a statement once.
                            # This is because likely multiple PCs together have the same
                            # location and are really the same statement.
                            # To increase the hit count by more than one, submit multiple txns.
                            continue

                        statement.hit_count += 1
                        handled_pcs.add(pc)
                        statements_hit.append(statement)

                        # Increment this function's hit count if we haven't already.
                        if inc_fn_hits and (
                            not functions_incremented
                            or function.full_name != functions_incremented[-1]
                        ):
                            function.hit_count += 1
                            functions_incremented.append(function.full_name)

        unhandled_pcs = set(pcs) - handled_pcs
        if unhandled_pcs:
            # Maybe a bug in ape.
            logger.debug(f"Unhandled PCs: '{','.join([f'{x}' for x in unhandled_pcs])}'")

        return handled_pcs, functions_incremented


class CoverageTracker(ManagerAccessMixin):
    def __init__(
        self,
        config_wrapper: ConfigWrapper,
        project: Optional[ProjectManager] = None,
        output_path: Optional[Path] = None,
    ):
        self.config_wrapper = config_wrapper
        self._project = project or self.local_project

        if output_path:
            self._output_path = output_path
        elif hasattr(self._project, "manifest_path"):
            # Local project.
            self._output_path = self._project.manifest_path.parent
        else:
            self._output_path = Path.cwd()

        # Data gets initialized lazily (if coverage is needed).
        self._data: Optional[CoverageData] = None

    @property
    def data(self) -> Optional[CoverageData]:
        if not self.config_wrapper.track_coverage:
            return None

        elif self._data is None:
            # First time being initialized.
            self._data = CoverageData(self._project, lambda: self._project._contract_sources)
            return self._data

        return self._data

    @property
    def enabled(self) -> bool:
        return self.config_wrapper.track_coverage

    @property
    def exclusions(self) -> list[ContractFunctionPath]:
        return self.config_wrapper.coverage_exclusions

    def reset(self):
        if self.data:
            self.data.reset()

    def cover(
        self,
        traceback: SourceTraceback,
        contract: Optional[str] = None,
        function: Optional[str] = None,
    ):
        """
        Track the coverage from the given source traceback.

        Args:
            traceback (:class:`~ape.types.trace.SourceTraceback`):
              The class instance containing all the information regarding
              sources covered for a particular transaction.
            contract (Optional[str]): Optionally provide the contract's name.
              This is needed when incrementing function hits that don't have
              any statements, such as auto-getters.
            function (Optional[str]): Optionally include function's full name
              to ensure its hit count is bumped, even when there are not statements
              found. This is the only way to bump hit counts for auto-getters.
        """
        if not self.data:
            return

        last_path: Optional[Path] = None
        last_pcs: set[int] = set()
        last_call: Optional[str] = None
        main_fn = None

        if (contract and not function) or (function and not contract):
            raise ValueError("Must provide both function and contract if supplying one of them.")

        elif contract and function:
            # Make sure it is the actual source.
            source_path = traceback[0].source_path if len(traceback) > 0 else None
            for project in self.data.report.projects:
                for src in project.sources:
                    # NOTE: We will allow this check to skip if there is no source is the
                    # traceback. This helps increment methods that are missing from the source map.
                    path = self._project.path / src.source_id
                    if source_path is not None and path != source_path:
                        continue

                    # Source containing the auto-getter found.
                    for con in src.contracts:
                        if con.name != contract:
                            continue

                        # Contract containing the auto-getter found.
                        for fn in con.functions:
                            if fn.full_name != function:
                                continue

                            # Auto-getter found.
                            main_fn = fn

        count_at_start = main_fn.hit_count if main_fn else None
        for control_flow in traceback:
            if not control_flow.source_path or not control_flow.pcs:
                continue

            new_pcs, new_funcs = self._cover(
                control_flow, last_path=last_path, last_pcs=last_pcs, last_call=last_call
            )
            if new_pcs:
                last_path = control_flow.source_path
                last_pcs = new_pcs

            if new_funcs:
                last_call = new_funcs[-1]

        if count_at_start is not None and main_fn and main_fn.hit_count == count_at_start:
            # If we get here, the control flow had no statements in it but yet
            # we were given contract and function information. This happens
            # for auto-getters where there are no source-map entries but the function
            # is still called. Thus, we need to bump the hit count for the auto-getter.
            main_fn.hit_count += 1

    def _cover(
        self,
        control_flow: ControlFlow,
        last_path: Optional[Path] = None,
        last_pcs: Optional[set[int]] = None,
        last_call: Optional[str] = None,
    ) -> tuple[set[int], list[str]]:
        if not self.data or control_flow.source_path is None:
            return set(), []

        last_pcs = last_pcs or set()
        pcs = control_flow.pcs
        if last_path is not None and control_flow.source_path == last_path:
            # Remove possibly duplicate PCs. This shouldn't happen,
            # but just in case the compiler made a mistake, we will
            # still get accurate coverage.
            new_pcs = pcs - last_pcs

        else:
            new_pcs = pcs

        inc_fn = last_call is None or last_call != control_flow.closure.full_name
        return self.data.cover(control_flow.source_path, new_pcs, inc_fn_hits=inc_fn)

    def hit_function(self, contract_source: ContractSource, method: MethodABI):
        """
        Another way to increment a function's hit count. Providers may not offer a
        way to trace calls but this method is available to still increment function
        hit counts.

        Args:
            contract_source (``ContractSource``): A contract with a known source file.
            method (``MethodABI``): The method called.
        """

        if not self.data:
            return

        for project in self.data.report.projects:
            for src in project.sources:
                if src.source_id != contract_source.source_id:
                    continue

                for contract in src.contracts:
                    if contract.name != contract_source.contract_type.name:
                        continue

                    for function in contract.functions:
                        if function.full_name != method.selector:
                            continue

                        function.hit_count += 1
                        return

    def show_session_coverage(self) -> bool:
        if not self.data or not self.data.report or not self.data.report.sources:
            return False

        # Reports are set in ape-config.yaml.
        reports = self.config_wrapper.ape_test_config.coverage.reports
        if reports.terminal:
            verbose = (
                reports.terminal.get("verbose", False)
                if isinstance(reports.terminal, dict)
                else False
            )
            if isinstance(verbose, str):
                verbose = verbose.lower()
                if verbose in ("true", "1", "t"):
                    verbose = True
                elif verbose in ("false", "0", "f"):
                    verbose = False
                else:
                    raise ValueError(f"Invalid value for `verbose` config '{verbose}'.")

            elif isinstance(verbose, int):
                verbose = bool(verbose)

            tables = parse_coverage_tables(
                self.data.report, verbose=verbose, statement=self.provider.supports_tracing
            )
            for idx, table in enumerate(tables):
                self.chain_manager._reports.echo(table)

                if idx < len(tables) - 1:
                    click.echo()

        if self.config_wrapper.xml_coverage:
            self.data.report.write_xml(self._output_path)
        if value := self.config_wrapper.html_coverage:
            verbose = value.get("verbose", False) if isinstance(value, dict) else False
            self.data.report.write_html(self._output_path, verbose=verbose)

        return True
