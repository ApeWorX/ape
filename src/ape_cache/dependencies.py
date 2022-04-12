from .db import SessionLocal
from contextlib import contextmanager


@contextmanager
def get_db():
    # Code to acquire resource, e.g.:
    db = SessionLocal()
    try:
        yield db
    finally:
        # Code to release resource, e.g.:
        db.close()