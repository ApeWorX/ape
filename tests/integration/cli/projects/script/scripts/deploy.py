from ape import networks

# Make sure the re-import bug goes away
from ._utils import deploy  # noqa: F401


def main():
    assert networks.active_provider is not None
    assert networks.active_provider.name == "test"
    print("Super secret script output")  # noqa: T001
