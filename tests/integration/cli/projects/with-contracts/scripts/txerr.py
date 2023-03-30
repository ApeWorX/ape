import ape


def main():
    """
    Cause an uncaught contract logic error to test traceback output.
    """
    account = ape.accounts.test_accounts[0]
    contract = account.deploy(ape.project.ContractA)

    # Fails.
    contract.setNumber(5, sender=account)
