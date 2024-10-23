from pathlib import Path

import pytest
from ethpm_types import MethodABI
from ethpm_types.source import ContractSource, Source

import ape
from ape.pytest.config import ConfigWrapper
from ape.pytest.coverage import CoverageData, CoverageTracker
from ape.types.coverage import (
    ContractCoverage,
    ContractSourceCoverage,
    CoverageProject,
    CoverageReport,
    CoverageStatement,
    FunctionCoverage,
)
from ape.types.trace import SourceTraceback

STMT_0_HIT = 12
STMT_1_HIT = 9
STMT_2_HIT = 0


@pytest.fixture
def statements():
    return create_statements(20, 21, 21)


def create_statements(*pcs) -> list[CoverageStatement]:
    return [
        CoverageStatement(pcs={pcs[0]}, hit_count=STMT_0_HIT),
        CoverageStatement(pcs={pcs[1]}, hit_count=STMT_1_HIT),
        CoverageStatement(pcs={pcs[2]}, hit_count=STMT_2_HIT),
    ]


@pytest.fixture
def foo_function(statements):
    return FunctionCoverage(name="foo", full_name="foo()", statements=statements, hit_count=1)


@pytest.fixture
def bar_function():
    return FunctionCoverage(
        name="bar", full_name="bar()", statements=create_statements(30, 31, 32), hit_count=0
    )


@pytest.fixture
def function(foo_function):
    return foo_function  # alias for when there's only 1 function in test.


@pytest.fixture
def contract(foo_function, bar_function):
    return ContractCoverage(name="Contract", functions=[foo_function, bar_function])


@pytest.fixture
def second_contract(foo_function, bar_function):
    # It's ok to have the same functions.
    return ContractCoverage(name="Contract_Second", functions=[foo_function, bar_function])


@pytest.fixture
def source_contract(contract):
    return ContractSourceCoverage(source_id="Contract.vy", contracts=[contract])


@pytest.fixture
def second_source_contract(second_contract):
    return ContractSourceCoverage(source_id="Contract_Second.vy", contracts=[second_contract])


@pytest.fixture
def coverage_project(source_contract, second_source_contract):
    return CoverageProject(name="__local__", sources=[source_contract, second_source_contract])


@pytest.fixture
def coverage_report(coverage_project):
    return CoverageReport(source_folders=[Path.cwd()], projects=[coverage_project], timestamp=0)


class TestFunctionCoverage:
    def test_hit_count(self, function):
        assert function.hit_count == 1

    def test_lines_coverage(self, function):
        assert function.lines_covered == 2

    def test_miss_count(self, function):
        assert function.miss_count == 1  # stmt 3

    def test_line_rate(self, function):
        assert function.line_rate == 2 / 3

    def test_line_rate_when_no_statements(self):
        """
        An edge case: when a function has no statements, its line rate
        it either 0% if it was not called or 100% if it called.
        """
        function = FunctionCoverage(name="bar", full_name="bar()")
        assert function.hit_count == 0
        function.hit_count += 1
        assert function.line_rate == 1


class TestContractCoverage:
    def test_function_rate(self, contract):
        assert contract.function_rate == 0.5

    def test_lines_coverage(self, contract):
        assert contract.lines_covered == 4

    def test_miss_count(self, contract):
        assert contract.miss_count == 2

    def test_line_rate(self, contract):
        assert contract.line_rate == 2 / 3


class TestSourceCoverage:
    def test_function_rate(self, source_contract):
        assert source_contract.function_rate == 0.5

    def test_lines_coverage(self, source_contract):
        assert source_contract.lines_covered == 4

    def test_miss_count(self, source_contract):
        assert source_contract.miss_count == 2

    def test_line_rate(self, source_contract):
        assert source_contract.line_rate == 2 / 3


class TestCoverageProject:
    def test_function_rate(self, coverage_project):
        assert coverage_project.function_rate == 0.5

    def test_lines_coverage(self, coverage_project):
        # Doubles because has 2 sources in it now (with same amounts of things)
        assert coverage_project.lines_covered == 8

    def test_miss_count(self, coverage_project):
        assert coverage_project.miss_count == 4

    def test_line_rate(self, coverage_project):
        assert coverage_project.line_rate == 2 / 3


class TestCoverageReport:
    def test_function_rate(self, coverage_report):
        assert coverage_report.function_rate == 0.5

    def test_lines_coverage(self, coverage_report):
        assert coverage_report.lines_covered == 8

    def test_miss_count(self, coverage_report):
        assert coverage_report.miss_count == 4

    def test_line_rate(self, coverage_report):
        assert coverage_report.line_rate == 2 / 3


class TestCoverageData:
    @pytest.fixture(scope="class")
    def src(self):
        return Source.model_validate("test")

    @pytest.fixture(scope="class")
    def contract_source(self, vyper_contract_type, src):
        return ContractSource(contract_type=vyper_contract_type, source=src)

    @pytest.fixture
    def coverage_data(self, project, contract_source):
        return CoverageData(project, (contract_source,))

    def test_report(self, coverage_data):
        actual = coverage_data.report
        assert isinstance(actual, CoverageReport)


class TestCoverageTracker:
    @pytest.fixture
    def pytest_config(self, mocker):
        return mocker.MagicMock()

    @pytest.fixture
    def config_wrapper(self, pytest_config):
        return ConfigWrapper(pytest_config)

    @pytest.fixture
    def tracker(self, pytest_config, project):
        return CoverageTracker(pytest_config, project=project)

    def test_data(self, tracker):
        assert tracker.data is not None
        actual = tracker.data.project
        expected = tracker.local_project
        assert actual == expected

    def test_cover(self, mocker, pytest_config, compilers, mock_compiler):
        """
        Ensure coverage of a call works.
        """
        filestem = "atest"
        filename = f"{filestem}.__mock__"
        fn_name = "_a_method"

        # Set up the mock compiler.
        mock_compiler.abi = [MethodABI(name=fn_name)]
        mock_compiler.ast = {
            "src": "0:112:0",
            "name": filename,
            "end_lineno": 7,
            "lineno": 1,
            "ast_type": "Module",
        }
        mock_compiler.pcmap = {"0": {"location": (1, 7, 1, 7)}}
        mock_contract = mocker.MagicMock()
        mock_contract.name = filename
        mock_statement = mocker.MagicMock()
        mock_statement.pcs = {20}
        mock_statement.hit_count = 0
        mock_function = mocker.MagicMock()
        mock_function.name = fn_name
        mock_function.statements = [mock_statement]
        mock_contract.functions = [mock_function]
        mock_contract.statements = [mock_statement]

        def init_profile(source_cov, src):
            source_cov.contracts = [mock_contract]

        mock_compiler.init_coverage_profile.side_effect = init_profile

        stmt = {"type": "dev: Cannot send ether to non-payable function", "pcs": [20]}
        fn_name = "_a_method"
        tb_data = {
            "statements": [stmt],
            "closure": {"name": fn_name, "full_name": f"{fn_name}()"},
            "depth": 0,
        }

        with ape.Project.create_temporary_project() as tmp:
            # Create a source file.
            file = tmp.path / "contracts" / filename
            file.parent.mkdir(exist_ok=True, parents=True)
            file.write_text("testing", encoding="utf8")

            # Ensure the TB refers to this source.
            tb_data["source_path"] = f"{tmp.path}/contracts/{filename}"
            call_tb = SourceTraceback.model_validate([tb_data])

            try:
                # Hack in our mock compiler.
                _ = compilers.registered_compilers  # Ensure cache is exists.
                compilers.__dict__["registered_compilers"][mock_compiler.ext] = mock_compiler

                # Ensure our coverage tracker is using our new tmp project w/ the new src
                # as well is set _after_ our new compiler plugin is added.
                tracker = CoverageTracker(pytest_config, project=tmp)

                tracker.cover(call_tb, contract=filestem, function=f"{fn_name}()")
                assert mock_statement.hit_count > 0

            finally:
                if (
                    "registered_compilers" in compilers.__dict__
                    and mock_compiler.ext in compilers.__dict__["registered_compilers"]
                ):
                    del compilers.__dict__["registered_compilers"][mock_compiler.ext]
