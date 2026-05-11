// NOTE: This is only here to show that we will not register "foundry-style" tests as contract tests

contract Test {
    function test_fails_if_registered() external {
        require(false, "Something wrong with pytest plugin for contract tests in `src/ape/pytest/plugin.py`.");
    }
}
