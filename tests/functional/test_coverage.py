from pathlib import Path
from typing import List

import pytest

from ape.types.coverage import (
    ContractCoverage,
    ContractSourceCoverage,
    CoverageProject,
    CoverageReport,
    CoverageStatement,
    FunctionCoverage,
)

STMT_0_HIT = 12
STMT_1_HIT = 9
STMT_2_HIT = 0


@pytest.fixture
def statements():
    return create_statements(20, 21, 21)


def create_statements(*pcs) -> List[CoverageStatement]:
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
