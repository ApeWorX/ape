import click
import pandas as pd
from sqlalchemy.orm import Session

from ape_cache.db import engine
import ape_cache.models as models
from .dependencies import get_db


@click.group(short_help="Query from caching database")
def cli():
    """
    Command-line helper for managing query caching database.
    """

@cli.command(short_help="Initialize a new cache db")
def init():
    models.Base.metadata.create_all(bind=engine)

@cli.command(short_help="Call and print SQL Statement to the cache db")
@click.argument("sql")
def query(sql):
    with get_db() as db:
        click.echo(pd.DataFrame(db.execute(sql)))

@cli.command(short_help="")
def migrate(db: Session = get_db):
    pass
