def __getattr__(name: str):
    if name == "abstractmethod":
        from abc import abstractmethod

        return abstractmethod

    elif name in (
        "LogInputABICollection",
        "Struct",
        "StructParser",
        "is_array",
        "is_dynamic_sized_type",
        "is_named_tuple",
        "is_struct",
        "returns_array",
    ):
        import ape.utils.abi as abi_module

        return getattr(abi_module, name)

    elif name in (
        "BaseInterface",
        "BaseInterfaceModel",
        "ExtraAttributesMixin",
        "ExtraModelAttributes",
        "ManagerAccessMixin",
        "injected_before_use",
        "only_raise_attribute_error",
    ):
        import ape.utils.basemodel as basemodel_module

        return getattr(basemodel_module, name)

    elif name in (
        "DEFAULT_LIVE_NETWORK_BASE_FEE_MULTIPLIER",
        "DEFAULT_LOCAL_TRANSACTION_ACCEPTANCE_TIMEOUT",
        "DEFAULT_TRANSACTION_ACCEPTANCE_TIMEOUT",
        "EMPTY_BYTES32",
        "LOCAL_NETWORK_NAME",
        "SOURCE_EXCLUDE_PATTERNS",
        "ZERO_ADDRESS",
        "add_padding_to_strings",
        "as_our_module",
        "cached_property",
        "extract_nested_value",
        "gas_estimation_error_message",
        "get_current_timestamp_ms",
        "get_package_version",
        "is_evm_precompile",
        "is_zero_hex",
        "load_config",
        "log_instead_of_fail",
        "nonreentrant",
        "pragma_str_to_specifier_set",
        "raises_not_implemented",
        "run_until_complete",
        "singledispatchmethod",
        "to_int",
    ):
        import ape.utils.misc as misc_module

        return getattr(misc_module, name)

    elif name in (
        "clean_path",
        "create_tempdir",
        "expand_environment_variables",
        "extract_archive",
        "get_all_files_in_directory",
        "get_full_extension",
        "get_package_path",
        "get_relative_path",
        "in_tempdir",
        "path_match",
        "run_in_tempdir",
        "use_temp_sys_path",
    ):
        import ape.utils.os as os_module

        return getattr(os_module, name)

    elif name in ("JoinableQueue", "spawn"):
        import ape.utils.process as process_module

        return getattr(process_module, name)

    elif name in (
        "USER_AGENT",
        "RPCHeaders",
        "allow_disconnected",
        "request_with_retry",
        "stream_response",
    ):
        import ape.utils.rpc as rpc_module

        return getattr(rpc_module, name)

    elif name in (
        "DEFAULT_NUMBER_OF_TEST_ACCOUNTS",
        "DEFAULT_TEST_ACCOUNT_BALANCE",
        "DEFAULT_TEST_CHAIN_ID",
        "DEFAULT_TEST_HD_PATH",
        "DEFAULT_TEST_MNEMONIC",
        "GeneratedDevAccount",
        "generate_dev_accounts",
    ):
        import ape.utils.testing as testing_module

        return getattr(testing_module, name)

    elif name in ("USER_ASSERT_TAG", "TraceStyles", "parse_coverage_tables", "parse_gas_table"):
        import ape.utils.trace as trace_module

        return getattr(trace_module, name)

    else:
        raise AttributeError(name)


__all__ = [
    "abstractmethod",
    "add_padding_to_strings",
    "allow_disconnected",
    "as_our_module",
    "BaseInterface",
    "BaseInterfaceModel",
    "cached_property",
    "clean_path",
    "create_tempdir",
    "DEFAULT_LIVE_NETWORK_BASE_FEE_MULTIPLIER",
    "DEFAULT_LOCAL_TRANSACTION_ACCEPTANCE_TIMEOUT",
    "DEFAULT_NUMBER_OF_TEST_ACCOUNTS",
    "DEFAULT_TEST_ACCOUNT_BALANCE",
    "DEFAULT_TEST_CHAIN_ID",
    "DEFAULT_TEST_MNEMONIC",
    "DEFAULT_TEST_HD_PATH",
    "DEFAULT_TRANSACTION_ACCEPTANCE_TIMEOUT",
    "EMPTY_BYTES32",
    "ExtraAttributesMixin",
    "expand_environment_variables",
    "extract_archive",
    "extract_nested_value",
    "ExtraModelAttributes",
    "get_relative_path",
    "gas_estimation_error_message",
    "get_package_version",
    "GeneratedDevAccount",
    "generate_dev_accounts",
    "get_all_files_in_directory",
    "get_current_timestamp_ms",
    "get_full_extension",
    "get_package_path",
    "pragma_str_to_specifier_set",
    "in_tempdir",
    "injected_before_use",
    "is_array",
    "is_dynamic_sized_type",
    "is_evm_precompile",
    "is_named_tuple",
    "is_struct",
    "is_zero_hex",
    "JoinableQueue",
    "load_config",
    "LOCAL_NETWORK_NAME",
    "log_instead_of_fail",
    "LogInputABICollection",
    "ManagerAccessMixin",
    "nonreentrant",
    "only_raise_attribute_error",
    "parse_coverage_tables",
    "parse_gas_table",
    "path_match",
    "raises_not_implemented",
    "returns_array",
    "request_with_retry",
    "RPCHeaders",
    "run_in_tempdir",
    "run_until_complete",
    "singledispatchmethod",
    "SOURCE_EXCLUDE_PATTERNS",
    "spawn",
    "stream_response",
    "Struct",
    "StructParser",
    "to_int",
    "TraceStyles",
    "use_temp_sys_path",
    "USER_AGENT",
    "USER_ASSERT_TAG",
    "ZERO_ADDRESS",
]
