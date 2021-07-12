from ape import networks


def main():
    assert networks.active_provider.name == "test"
    print("Script ran!")
