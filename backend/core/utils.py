"""Small, dependency-free utilities."""

from __future__ import annotations

from datetime import datetime, timezone


def timestamp_to_iso(unix_timestamp: int) -> str:
    """Convert a Unix timestamp (seconds) to ISO 8601 with ``Z`` suffix."""
    dt = datetime.fromtimestamp(unix_timestamp, tz=timezone.utc)
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def iso_to_timestamp(time_str: str) -> int:
    """Parse an ISO 8601 string (with ``Z`` or offset) to Unix seconds."""
    if time_str.endswith("Z"):
        time_str = time_str[:-1] + "+00:00"
    dt = datetime.fromisoformat(time_str)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return int(dt.timestamp())


def short_hash(value: str, length: int = 8) -> str:
    """Return a short prefix of a hash for logging."""
    return value[:length] if len(value) > length else value