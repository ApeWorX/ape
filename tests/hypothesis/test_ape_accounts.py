# This test code was written by the `hypothesis.extra.ghostwriter` module
# and is provided under the Creative Commons Zero public domain dedication.

from pathlib import Path

from hypothesis import given
from hypothesis import strategies as st

import ape_accounts.accounts
from ape.api.accounts import AccountAPI


@given(data_folder=st.builds(Path), account_type=st.just(AccountAPI))
def test_fuzz_AccountContainer(data_folder, account_type):
    ape_accounts.accounts.AccountContainer(data_folder=data_folder, account_type=account_type)


@given(keyfile_path=st.builds(Path), locked=st.booleans())
def test_fuzz_KeyfileAccount(keyfile_path, locked):
    ape_accounts.accounts.KeyfileAccount(keyfile_path=keyfile_path, locked=locked)
