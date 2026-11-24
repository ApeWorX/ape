from collections.abc import Iterator
from typing import TYPE_CHECKING

import pytest

from ape.utils import ManagerAccessMixin

if TYPE_CHECKING:
    from .module import ContractTestModule


class ContractTestCollector(pytest.File, ManagerAccessMixin):
    """Collect Contract Type(s) into Module(s) from compiling file with a supported compiler."""

    # TODO: `.compile_settings -> dict` to add test-only remappings
    # TODO: Add `.local_project` to compiler settings
    # TODO: Update Test-only compile config via `self.config_manager.get(...)`?
    # TODO: Extend CompilerAPI plugin settings via `self.compiler.test_settings()`
    # TODO: Support config settings via `.config` (from pytest config)

    def collect(self) -> Iterator["ContractTestModule"]:
        if not (compiler := self.compiler_manager.registered_compilers.get(self.path.suffix)):
            # TODO: Create a warning about missing compiler for extension?
            return

        from .module import ContractTestModule

        with self.chain_manager.contracts.use_temporary_caches():
            for contract_type in compiler.compile(
                [self.path],
                # TODO: Use `settings=self.compile_settings` for test-only compile settings?
                #       Allows configuring extra test-only deps (e.g. `from ape.project import IContract`)
            ):
                # TODO: Migrate Stateful testing detection here? Might make more sense
                yield ContractTestModule.from_parent(
                    self,
                    name=contract_type.name,
                    contract_type=contract_type,
                )
