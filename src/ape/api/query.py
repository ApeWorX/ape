import pandas as pd

from ape.types import Query


class QueryAPI:
    def estimate_query(self, query: Query) -> pd.DataFrame:
        """
        Estimation of time needed to complete the query.

        Args:
            query (``Query``): query to estimate

        Returns:
            pandas.DataFrame
        """
        pass

    def perform_query(self, query: Query) -> pd.DataFrame:
        """
        Executes the query using best performing ``estimate_query`` query engine.

        Args:
            query (``Query``): query to execute

        Returns:
            pandas.DataFrame
        """
        pass
