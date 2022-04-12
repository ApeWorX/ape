"""
sub-class the QueryAPI
move the default_query_provider here
Some refactoring that has to be done

2nd step:
Third method added to QueryAPI (update_cache) defaults to doing nothing
override QueryAPI.update_cache
start pushing queries to be on_disk (sqlite)
push the sqlite database to the data folder
update the first two methods to first query the database, if exists, respond with data from
that databases, else go to provider to get raw data

Research the database schema
"""
from ape.managers.query import DefaultQueryProvider


class QueryManager(DefaultQueryProvider):

    def __init__(self):
        self.db = get_db()

    def does_query_exist(self):
        """
        SQLAlchemy ORM to SQLite database
        Checks for exact query
        """

    def query_cache(self):
        """
        if query exists
        query the cache database
        """

    def query_provider(self):
        """
        if query does not exist
        query the provider
        """
