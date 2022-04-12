import click
from sqlalchemy.orm import Session

from .dependencies import get_db


@click.group(short_help="Query from caching database")
def cli(use_cache, db: Session = get_db):
    """
    Command-line helper for managing query caching database.
    """

@cli.command(short_help="Initialize a new cache db")
def init():
    db = get_db()
    db.init()

@cli.command(short_help="")
def migrate():
    db = get_db()