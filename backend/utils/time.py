"""Shared datetime helpers."""
from datetime import datetime, timezone


def as_utc(dt: datetime) -> datetime:
    """Re-tag a datetime read back from the database as UTC before comparing.

    SQLite round-trips DateTime(timezone=True) values naive; Postgres returns
    aware ones. Everything the app writes is UTC, so re-tagging is lossless
    and makes naive and aware values comparable.
    """
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
