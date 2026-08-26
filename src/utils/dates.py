"""Shared date parsing for tools and session persistence."""

from datetime import datetime, timezone


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    if len(value) == 10:
        return datetime.fromisoformat(value + "T00:00:00+00:00")
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def parse_dt(value: str | None) -> datetime:
    """Parse stored ISO timestamp; fall back to now when missing."""
    if not value:
        return utc_now()
    return datetime.fromisoformat(value.replace("Z", "+00:00"))
