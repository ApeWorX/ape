def cli():
    """
    This script tests the scenario when a cli script is missing
    a click-decorator. The script itself is not runnable by Ape,
    but it will cause a warning. Primarily, it is important that
    it does not cause the entire scripts-integration to fail.
    """
