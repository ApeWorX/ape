from .db import SessionLocal
from contextlib import contextmanager


@contextmanager
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()