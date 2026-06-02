import calendar
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Optional

from models.enums import TimeRange

__all__ = ["DateRange", "resolve_time_range"]


@dataclass
class DateRange:
    start: date
    end: date
    from_key: int      # YYYYMMDD integer
    to_key: int        # YYYYMMDD integer
    window_days: int   # calendar days in window — used for prior-period momentum
    prior_start: date
    prior_end: date
    prior_from_key: int
    prior_to_key: int


def _to_key(d: date) -> int:
    return int(d.strftime("%Y%m%d"))


def _last_day(year: int, month: int) -> int:
    return calendar.monthrange(year, month)[1]


def resolve_time_range(tr: TimeRange, as_of_date: Optional[date] = None) -> DateRange:
    """
    Resolve a TimeRange enum to a concrete DateRange.

    Pass as_of_date to anchor trailing windows to a historical date instead of
    today — enables reproducible / backtesting queries.
    """
    today = as_of_date or date.today()

    if tr == TimeRange.trailing_7:
        start = today - timedelta(days=7)
        end = today
        prior_start = start - timedelta(days=7)
        prior_end = start - timedelta(days=1)

    elif tr == TimeRange.trailing_30:
        start = today - timedelta(days=30)
        end = today
        prior_start = start - timedelta(days=30)
        prior_end = start - timedelta(days=1)

    elif tr == TimeRange.trailing_90:
        start = today - timedelta(days=90)
        end = today
        prior_start = start - timedelta(days=90)
        prior_end = start - timedelta(days=1)

    elif tr == TimeRange.last_month:
        first_this_month = today.replace(day=1)
        last_day_prev = first_this_month - timedelta(days=1)
        start = last_day_prev.replace(day=1)
        end = last_day_prev
        prior_end = start - timedelta(days=1)
        prior_start = prior_end.replace(day=1)

    elif tr == TimeRange.last_quarter:
        q = (today.month - 1) // 3  # current quarter index (0-based)
        if q == 0:
            start = date(today.year - 1, 10, 1)
            end = date(today.year - 1, 12, 31)
        else:
            start = date(today.year, (q - 1) * 3 + 1, 1)
            end_month = q * 3
            end = date(today.year, end_month, _last_day(today.year, end_month))
        prior_days = (end - start).days + 1
        prior_end = start - timedelta(days=1)
        prior_start = prior_end - timedelta(days=prior_days - 1)

    elif tr == TimeRange.ytd:
        start = today.replace(month=1, day=1)
        end = today
        prior_start = start.replace(year=start.year - 1)
        prior_end = end.replace(year=end.year - 1)

    elif tr == TimeRange.l12m:
        start = today - timedelta(days=365)
        end = today
        prior_start = start - timedelta(days=365)
        prior_end = start - timedelta(days=1)

    else:
        raise ValueError(f"Unknown time_range: {tr}")

    window_days = (end - start).days + 1

    return DateRange(
        start=start,
        end=end,
        from_key=_to_key(start),
        to_key=_to_key(end),
        window_days=window_days,
        prior_start=prior_start,
        prior_end=prior_end,
        prior_from_key=_to_key(prior_start),
        prior_to_key=_to_key(prior_end),
    )
