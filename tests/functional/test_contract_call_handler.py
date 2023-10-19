def test_struct_input(
    call_handler_with_struct_input, struct_input_for_call, output_from_struct_input_call
):
    actual = call_handler_with_struct_input.encode_input(*struct_input_for_call)
    assert actual == output_from_struct_input_call
