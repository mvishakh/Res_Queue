from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


def utcnow() -> datetime:
    return datetime.now(UTC)


def business_date(now: datetime, tz_name: str) -> date:
    """The restaurant-local calendar date, used to reset queue numbers daily."""
    try:
        tz = ZoneInfo(tz_name)
    except ZoneInfoNotFoundError:
        tz = ZoneInfo("UTC")
    return now.astimezone(tz).date()
