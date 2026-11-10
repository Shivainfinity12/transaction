"""Shared fixtures for the Step 5 (Backend Connection) tests.

Patches sqlite3.connect so that every get_db() call — in database.db,
database.queries and app — points at a fresh temp database seeded with the
real init_db()/seed_db() helpers. This keeps tests isolated from the dev
spendly.db file.
"""

import os
import sqlite3
import sys

import pytest

# Make the repo root importable regardless of where pytest is invoked from.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import database.db as database_db
from database.db import init_db, seed_db


@pytest.fixture()
def seeded_db(tmp_path, monkeypatch):
    """Fresh temp SQLite DB with the real schema + seed data.

    Every sqlite3.connect() call made through database.db (and therefore
    through get_db()) is redirected to the temp file for the duration of
    the test.
    """
    db_path = tmp_path / "test_spendly.db"
    real_connect = sqlite3.connect

    def fake_connect(_path, *args, **kwargs):
        return real_connect(str(db_path), *args, **kwargs)

    monkeypatch.setattr(database_db.sqlite3, "connect", fake_connect)
    init_db()
    seed_db()
    return db_path


@pytest.fixture()
def client(seeded_db):
    """Flask test client bound to the seeded temp database."""
    import app as app_module

    app_module.app.config["TESTING"] = True
    with app_module.app.test_client() as test_client:
        yield test_client
