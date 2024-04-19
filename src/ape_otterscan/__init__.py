from ape import plugins
from ape_otterscan.query import OTSQueryEngine


@plugins.register(plugins.QueryPlugin)
def query_engines():
    yield OTSQueryEngine
