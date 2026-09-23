"""Tests for the Alembic migration chain against a fresh database.

The app's startup path runs ``alembic upgrade head`` on a file-based SQLite
database. These tests run the same migrations against a throwaway database
and assert the resulting schema matches the SQLAlchemy models — this guards
against migrations drifting from ``db/models.py`` (e.g. a new model table
being added without a corresponding migration).
"""

from pathlib import Path

import pytest

import db.database as db_database
from db.models import Base

BACKEND_ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture()
def migrated_db_path(tmp_path, monkeypatch):
    """Run ``alembic upgrade head`` against a throwaway SQLite file."""
    from alembic import command
    from alembic.config import Config

    db_path = str(tmp_path / "migration-test.db")
    # migrations/env.py resolves the target URL from db.database.DB_PATH at
    # migration time, so point that attribute at the throwaway file (restored
    # automatically after the test). The async engine used by the rest of the
    # test session stays on :memory: and is unaffected.
    monkeypatch.setattr(db_database, "DB_PATH", db_path)

    cfg = Config(str(BACKEND_ROOT / "alembic.ini"))
    command.upgrade(cfg, "head")
    return db_path


def _read_tables(db_path: str) -> set[str]:
    conn = __import__("sqlite3").connect(db_path)
    try:
        return {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    finally:
        conn.close()


def test_upgrade_head_creates_all_model_tables(migrated_db_path):
    actual = _read_tables(migrated_db_path)

    for table in Base.metadata.tables:
        assert table in actual, f"table {table!r} missing after `alembic upgrade head`"


def test_upgrade_head_matches_model_columns(migrated_db_path):
    """Every model column exists in the migrated schema (order-insensitive)."""
    import sqlite3

    conn = sqlite3.connect(migrated_db_path)
    try:
        for table in Base.metadata.tables.values():
            actual_cols = {row[1] for row in conn.execute(f"PRAGMA table_info({table.name})")}
            missing = set(table.columns.keys()) - actual_cols
            assert not missing, f"table {table.name} is missing columns after migration: {missing}"
    finally:
        conn.close()


def test_upgrade_head_is_idempotent(migrated_db_path):
    """Re-running upgrade on an up-to-date DB is a no-op, not an error."""
    from alembic import command
    from alembic.config import Config

    cfg = Config(str(BACKEND_ROOT / "alembic.ini"))
    command.upgrade(cfg, "head")  # must not raise

    assert "oauth_identities" in _read_tables(migrated_db_path)


def test_recruiter_flag_backfilled_from_role(tmp_path, monkeypatch):
    """Users who had role='recruiter' before the flag existed keep access."""
    import sqlite3

    from alembic import command
    from alembic.config import Config

    db_path = str(tmp_path / "backfill-test.db")
    monkeypatch.setattr(db_database, "DB_PATH", db_path)
    cfg = Config(str(BACKEND_ROOT / "alembic.ini"))

    # Build the schema as it was before the flag (pre-6f34e3e1eca3), then
    # add pre-flag users whose role strings the flag backfill acted on.
    command.upgrade(cfg, "b8e2802f0d1b")
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            "INSERT INTO users (id, email, name, provider, provider_id, role, created_at, last_login_at) "
            "VALUES ('u1', 'a@x.com', 'A', 'google', 'p1', 'recruiter', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP),"
            "('u2', 'b@x.com', 'B', 'google', 'p2', 'candidate', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
        )
        conn.commit()
    finally:
        conn.close()

    # Upgrading to head passes through b2c3d4e5f6a7, which folds the flag
    # the 6f34e3e1eca3 backfill set into role. u1 (role='recruiter') keeps
    # recruiter; u2 (role='candidate', no grant) stays candidate.
    command.upgrade(cfg, "head")

    conn = sqlite3.connect(db_path)
    try:
        cols = {row[1] for row in conn.execute("PRAGMA table_info(users)")}
        roles = dict(conn.execute("SELECT id, role FROM users"))
    finally:
        conn.close()
    assert "is_recruiter" not in cols
    assert roles == {"u1": "recruiter", "u2": "candidate"}

def test_exclusive_roles_migration_resolves_flag_and_drops_column(tmp_path, monkeypatch):
    """b2c3d4e5f6a7: the recruiter grant wins over the last-picked mode string."""
    import sqlite3

    from alembic import command
    from alembic.config import Config

    db_path = str(tmp_path / "exclusive-roles-test.db")
    monkeypatch.setattr(db_database, "DB_PATH", db_path)
    cfg = Config(str(BACKEND_ROOT / "alembic.ini"))

    # Build the dual-role schema (flag column present) and insert every
    # combination that could exist in a live database.
    command.upgrade(cfg, "e7f8a9b0c1d2")
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            "INSERT INTO users (id, email, name, provider, provider_id, role, is_recruiter, created_at, last_login_at) "
            "VALUES "
            "('u1', 'dual@x.com', 'D', 'google', 'p1', 'candidate', 1, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP),"
            "('u2', 'rec@x.com', 'R', 'google', 'p2', 'recruiter', 1, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP),"
            "('u3', 'admin@x.com', 'A', 'google', 'p3', 'admin', 1, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP),"
            "('u4', 'plain@x.com', 'P', 'google', 'p4', 'candidate', 0, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
        )
        conn.commit()
    finally:
        conn.close()

    command.upgrade(cfg, "head")

    conn = sqlite3.connect(db_path)
    try:
        cols = {row[1] for row in conn.execute("PRAGMA table_info(users)")}
        roles = dict(conn.execute("SELECT id, role FROM users"))
    finally:
        conn.close()
    # Grant wins for the dual-role candidate; admins are untouched.
    assert roles == {
        "u1": "recruiter",
        "u2": "recruiter",
        "u3": "admin",
        "u4": "candidate",
    }
    # The flag column is gone — role is the single source of truth.
    assert "is_recruiter" not in cols
