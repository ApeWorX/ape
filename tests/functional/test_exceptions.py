from ape.cli import Abort


def test_abort():
    assert str(Abort()) == "Operation aborted in test_exceptions.py::test_abort on line 5."
