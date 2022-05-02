# This test code was written by the `hypothesis.extra.ghostwriter` module
# and is provided under the Creative Commons Zero public domain dedication.

from hypothesis import given
from hypothesis import strategies as st

import ape.cli
from ape.api.accounts import AccountAPI


@given(message=st.one_of(st.none(), st.text()))
def test_fuzz_Abort(message):
    ape.cli.Abort(message=message)


@given(
    account_type=st.one_of(st.none(), st.just(AccountAPI)),
    prompt_message=st.one_of(st.none(), st.text()),
)
def test_fuzz_AccountAliasPromptChoice(account_type, prompt_message):
    ape.cli.AccountAliasPromptChoice(account_type=account_type, prompt_message=prompt_message)


@given(account_type=st.one_of(st.none(), st.just(AccountAPI)))
def test_fuzz_Alias(account_type):
    ape.cli.Alias(account_type=account_type)


@given(help=st.none(), required=st.booleans(), multiple=st.booleans())
def test_fuzz_contract_option(help, required, multiple):
    ape.cli.contract_option(help=help, required=required, multiple=multiple)


@given(account_type=st.one_of(st.none(), st.just(AccountAPI)))
def test_fuzz_existing_alias_argument(account_type):
    ape.cli.existing_alias_argument(account_type=account_type)


@given(options=st.one_of(st.none(), st.lists(st.sampled_from(ape.cli.choices.OutputFormat))))
def test_fuzz_output_format_choice(options):
    ape.cli.output_format_choice(options=options)


@given(default=st.sampled_from(ape.cli.choices.OutputFormat))
def test_fuzz_output_format_option(default):
    ape.cli.output_format_option(default=default)


@given(help=st.text())
def test_fuzz_skip_confirmation_option(help):
    ape.cli.skip_confirmation_option(help=help)
