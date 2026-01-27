"""
Time Filter Parser for Trace

Parses natural language time references to date ranges for filtering
notes and search results.

Supported formats:
- Relative: "today", "yesterday", "this week", "last month", "last 7 days"
- Weekdays: "last Saturday", "this Monday", "next Friday"
- Named periods: "January", "January 2025", "Q1 2025", "2025"
- Date ranges: "Jan 1 to Jan 15", "from 2025-01-01 to 2025-01-15"
- Specific dates: "January 15, 2025", "2025-01-15", "Jan 15"

P7-01: Time filter parser
"""

import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Literal

logger = logging.getLogger(__name__)


@dataclass
class TimeFilter:
    """A time range filter for queries."""

    start: datetime
    end: datetime
    description: str
    confidence: float = 1.0

    def contains(self, dt: datetime) -> bool:
        """Check if a datetime is within this filter."""
        return self.start <= dt <= self.end

    def overlaps(self, start: datetime, end: datetime) -> bool:
        """Check if a date range overlaps with this filter."""
        return self.start <= end and start <= self.end

    def to_dict(self) -> dict:
        """Convert to dictionary representation."""
        return {
            "start": self.start.isoformat(),
            "end": self.end.isoformat(),
            "description": self.description,
            "confidence": self.confidence,
        }


@dataclass
class TimeParseResult:
    """Result of parsing a time expression with ambiguity detection."""

    time_filter: TimeFilter | None
    confidence: float  # 0.0-1.0
    ambiguous: bool = False
    clarification_options: list[str] = field(default_factory=list)
    raw_expression: str = ""

    def to_dict(self) -> dict:
        """Convert to dictionary representation."""
        return {
            "time_filter": self.time_filter.to_dict() if self.time_filter else None,
            "confidence": self.confidence,
            "ambiguous": self.ambiguous,
            "clarification_options": self.clarification_options,
            "raw_expression": self.raw_expression,
        }


# Regex patterns for time parsing
PATTERNS = {
    # Relative patterns
    "today": re.compile(r"\b(today)\b", re.IGNORECASE),
    "yesterday": re.compile(r"\b(yesterday)\b", re.IGNORECASE),
    "this_week": re.compile(r"\b(this\s+week)\b", re.IGNORECASE),
    "last_week": re.compile(r"\b(last\s+week)\b", re.IGNORECASE),
    "this_month": re.compile(r"\b(this\s+month)\b", re.IGNORECASE),
    "last_month": re.compile(r"\b(last\s+month)\b", re.IGNORECASE),
    "this_year": re.compile(r"\b(this\s+year)\b", re.IGNORECASE),
    "last_year": re.compile(r"\b(last\s+year)\b", re.IGNORECASE),
    # Weekday patterns
    "last_weekday": re.compile(
        r"\blast\s+(monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b",
        re.IGNORECASE,
    ),
    "this_weekday": re.compile(
        r"\bthis\s+(monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b",
        re.IGNORECASE,
    ),
    # "Last [month name]" without year - potentially ambiguous
    "last_month_name": re.compile(
        r"\blast\s+(january|february|march|april|may|june|july|august|september|october|november|december)\b",
        re.IGNORECASE,
    ),
    # Last N days/weeks/months
    "last_n_days": re.compile(r"\b(?:(?:the\s+)?last|past)\s+(\d+)\s+days?\b", re.IGNORECASE),
    "last_n_weeks": re.compile(r"\b(?:(?:the\s+)?last|past)\s+(\d+)\s+weeks?\b", re.IGNORECASE),
    "last_n_months": re.compile(r"\b(?:(?:the\s+)?last|past)\s+(\d+)\s+months?\b", re.IGNORECASE),
    # N days/weeks/months ago
    "n_days_ago": re.compile(r"\b(\d+)\s+days?\s+ago\b", re.IGNORECASE),
    "n_weeks_ago": re.compile(r"\b(\d+)\s+weeks?\s+ago\b", re.IGNORECASE),
    # Month names (with optional year)
    "month_year": re.compile(
        r"\b(january|february|march|april|may|june|july|august|september|october|november|december)"
        r"(?:\s+(\d{4}))?\b",
        re.IGNORECASE,
    ),
    # Just a year
    "year_only": re.compile(r"\b(20\d{2})\b"),
    # Quarter
    "quarter": re.compile(r"\b(Q[1-4])\s*(\d{4})?\b", re.IGNORECASE),
    # ISO date
    "iso_date": re.compile(r"\b(\d{4}-\d{2}-\d{2})\b"),
    # Month day, year
    "month_day_year": re.compile(
        r"\b(january|february|march|april|may|june|july|august|september|october|november|december)"
        r"\s+(\d{1,2})(?:st|nd|rd|th)?,?\s*(\d{4})?\b",
        re.IGNORECASE,
    ),
    # Short month day
    "short_month_day": re.compile(
        r"\b(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)"
        r"\s+(\d{1,2})(?:st|nd|rd|th)?(?:,?\s*(\d{4}))?\b",
        re.IGNORECASE,
    ),
    # Date range with "to" or "-" or "through"
    "date_range": re.compile(
        r"\b(?:from\s+)?(.+?)\s+(?:to|through|-)\s+(.+?)(?:\s|$)", re.IGNORECASE
    ),
    # Between X and Y
    "between": re.compile(r"\bbetween\s+(.+?)\s+and\s+(.+?)(?:\s|$)", re.IGNORECASE),
    # On (specific date)
    "on_date": re.compile(r"\bon\s+(.+?)(?:\s|$)", re.IGNORECASE),
    # During (period)
    "during": re.compile(r"\bduring\s+(.+?)(?:\s|$)", re.IGNORECASE),
    # Since (date)
    "since": re.compile(r"\bsince\s+(.+?)(?:\s|$)", re.IGNORECASE),
    # Before/after
    "before": re.compile(r"\bbefore\s+(.+?)(?:\s|$)", re.IGNORECASE),
    "after": re.compile(r"\bafter\s+(.+?)(?:\s|$)", re.IGNORECASE),
    # Ordinal day only (e.g., "the 25th", "on the 25th")
    "ordinal_day": re.compile(r"\b(?:the\s+)?(\d{1,2})(?:st|nd|rd|th)\b", re.IGNORECASE),
}

# Month name to number mapping
MONTH_MAP = {
    "january": 1,
    "jan": 1,
    "february": 2,
    "feb": 2,
    "march": 3,
    "mar": 3,
    "april": 4,
    "apr": 4,
    "may": 5,
    "june": 6,
    "jun": 6,
    "july": 7,
    "jul": 7,
    "august": 8,
    "aug": 8,
    "september": 9,
    "sep": 9,
    "october": 10,
    "oct": 10,
    "november": 11,
    "nov": 11,
    "december": 12,
    "dec": 12,
}

# Weekday name to Python weekday number (Monday=0, Sunday=6)
WEEKDAY_MAP = {
    "monday": 0,
    "tuesday": 1,
    "wednesday": 2,
    "thursday": 3,
    "friday": 4,
    "saturday": 5,
    "sunday": 6,
}

# Reverse mapping for display
WEEKDAY_NAMES = {v: k.title() for k, v in WEEKDAY_MAP.items()}
MONTH_NAMES = {v: k.title() for k, v in MONTH_MAP.items() if len(k) > 3}


def _start_of_day(dt: datetime) -> datetime:
    """Get the start of a day."""
    return dt.replace(hour=0, minute=0, second=0, microsecond=0)


def _end_of_day(dt: datetime) -> datetime:
    """Get the end of a day."""
    return dt.replace(hour=23, minute=59, second=59, microsecond=999999)


def _start_of_week(dt: datetime) -> datetime:
    """Get the start of the week (Monday)."""
    days_since_monday = dt.weekday()
    return _start_of_day(dt - timedelta(days=days_since_monday))


def _end_of_week(dt: datetime) -> datetime:
    """Get the end of the week (Sunday)."""
    days_until_sunday = 6 - dt.weekday()
    return _end_of_day(dt + timedelta(days=days_until_sunday))


def _start_of_month(dt: datetime) -> datetime:
    """Get the start of the month."""
    return _start_of_day(dt.replace(day=1))


def _end_of_month(dt: datetime) -> datetime:
    """Get the end of the month."""
    # Move to next month and subtract a day
    if dt.month == 12:
        next_month = dt.replace(year=dt.year + 1, month=1, day=1)
    else:
        next_month = dt.replace(month=dt.month + 1, day=1)
    return _end_of_day(next_month - timedelta(days=1))


def _start_of_year(dt: datetime) -> datetime:
    """Get the start of the year."""
    return _start_of_day(dt.replace(month=1, day=1))


def _end_of_year(dt: datetime) -> datetime:
    """Get the end of the year."""
    return _end_of_day(dt.replace(month=12, day=31))


def _get_quarter_range(quarter: int, year: int) -> tuple[datetime, datetime]:
    """Get the start and end dates for a quarter."""
    quarter_starts = {
        1: (1, 1),
        2: (4, 1),
        3: (7, 1),
        4: (10, 1),
    }
    quarter_ends = {
        1: (3, 31),
        2: (6, 30),
        3: (9, 30),
        4: (12, 31),
    }

    start_month, start_day = quarter_starts[quarter]
    end_month, end_day = quarter_ends[quarter]

    start = _start_of_day(datetime(year, start_month, start_day))
    end = _end_of_day(datetime(year, end_month, end_day))

    return start, end


def _resolve_last_weekday(weekday_name: str, reference: datetime) -> tuple[datetime, datetime]:
    """
    Find the most recent occurrence of a weekday before today.

    "last Monday" on a Monday means the Monday 7 days ago.
    "last Monday" on a Tuesday means yesterday (if Monday).

    Args:
        weekday_name: Name of the weekday (e.g., "monday", "saturday")
        reference: Reference datetime

    Returns:
        Tuple of (start_of_day, end_of_day) for the target date
    """
    target_weekday = WEEKDAY_MAP[weekday_name.lower()]
    current_weekday = reference.weekday()

    # Calculate days back to the target weekday
    days_back = (current_weekday - target_weekday) % 7
    if days_back == 0:
        days_back = 7  # "last Monday" on a Monday means 7 days ago

    target_date = reference - timedelta(days=days_back)
    return (_start_of_day(target_date), _end_of_day(target_date))


def _resolve_this_weekday(weekday_name: str, reference: datetime) -> tuple[datetime, datetime]:
    """
    Find the occurrence of a weekday in the current week.

    "this Monday" returns this week's Monday (past or future).

    Args:
        weekday_name: Name of the weekday
        reference: Reference datetime

    Returns:
        Tuple of (start_of_day, end_of_day) for the target date
    """
    target_weekday = WEEKDAY_MAP[weekday_name.lower()]
    current_weekday = reference.weekday()

    # Calculate days difference (can be negative for past days in week)
    days_diff = target_weekday - current_weekday
    target_date = reference + timedelta(days=days_diff)

    return (_start_of_day(target_date), _end_of_day(target_date))


def _resolve_month_reference(
    month_name: str, reference: datetime, is_last: bool = False
) -> TimeParseResult:
    """
    Resolve a month-only reference with ambiguity detection.

    "last July" in January 2026 is ambiguous - could mean:
    - July 2025 (more recent)
    - July 2024 (year before that)

    "July" without "last" in January 2026 defaults to the most recent July.

    Args:
        month_name: Name of the month
        reference: Reference datetime
        is_last: Whether "last" prefix was used

    Returns:
        TimeParseResult with ambiguity information if applicable
    """
    target_month = MONTH_MAP.get(month_name.lower(), MONTH_MAP.get(month_name[:3].lower()))
    if not target_month:
        return TimeParseResult(time_filter=None, confidence=0.0, raw_expression=month_name)

    current_month = reference.month
    current_year = reference.year

    # Determine the most likely year for this month
    if target_month < current_month:
        # Month is earlier in the year - most recent occurrence is this year
        primary_year = current_year
        alternate_year = current_year - 1
    elif target_month > current_month:
        # Month is later in the year - most recent complete occurrence is last year
        primary_year = current_year - 1
        alternate_year = current_year - 2
    else:
        # Same month - if "last" used, go to previous year; otherwise current
        if is_last:
            primary_year = current_year - 1
            alternate_year = current_year - 2
        else:
            primary_year = current_year
            alternate_year = current_year - 1

    # Build the primary time filter
    start = _start_of_day(datetime(primary_year, target_month, 1))
    end = _end_of_month(start)
    primary_filter = TimeFilter(
        start=start,
        end=end,
        description=f"{MONTH_NAMES.get(target_month, month_name.title())} {primary_year}",
    )

    # Determine if this is ambiguous
    # "last July" is ambiguous if we're in the first half of the year
    # and the month is before the current month
    is_ambiguous = is_last and (
        # Early in the year, "last July" could mean last year or year before
        (current_month <= 6 and target_month > 6)
        or
        # Or if we're close to the target month
        (abs(current_month - target_month) <= 2 and current_month != target_month)
    )

    if is_ambiguous:
        return TimeParseResult(
            time_filter=primary_filter,
            confidence=0.6,
            ambiguous=True,
            clarification_options=[
                f"{MONTH_NAMES.get(target_month, month_name.title())} {primary_year}",
                f"{MONTH_NAMES.get(target_month, month_name.title())} {alternate_year}",
            ],
            raw_expression=f"last {month_name}" if is_last else month_name,
        )

    return TimeParseResult(
        time_filter=primary_filter,
        confidence=0.9,
        ambiguous=False,
        raw_expression=f"last {month_name}" if is_last else month_name,
    )


def _parse_single_date(text: str, reference: datetime) -> datetime | None:
    """
    Parse a single date from text.

    Args:
        text: Text to parse
        reference: Reference datetime for relative dates

    Returns:
        Parsed datetime or None
    """
    text = text.strip()

    # Try ISO date
    iso_match = PATTERNS["iso_date"].search(text)
    if iso_match:
        try:
            return datetime.fromisoformat(iso_match.group(1))
        except ValueError:
            pass

    # Try month day, year
    mdy_match = PATTERNS["month_day_year"].search(text)
    if mdy_match:
        month_name = mdy_match.group(1).lower()
        day = int(mdy_match.group(2))
        year = int(mdy_match.group(3)) if mdy_match.group(3) else reference.year

        month = MONTH_MAP.get(month_name, MONTH_MAP.get(month_name[:3]))
        if month:
            try:
                return datetime(year, month, day)
            except ValueError:
                pass

    # Try short month day
    smd_match = PATTERNS["short_month_day"].search(text)
    if smd_match:
        month_name = smd_match.group(1).lower()
        day = int(smd_match.group(2))
        year = int(smd_match.group(3)) if smd_match.group(3) else reference.year

        month = MONTH_MAP.get(month_name, MONTH_MAP.get(month_name[:3]))
        if month:
            try:
                return datetime(year, month, day)
            except ValueError:
                pass

    # Try month year
    my_match = PATTERNS["month_year"].search(text)
    if my_match:
        month_name = my_match.group(1).lower()
        year = int(my_match.group(2)) if my_match.group(2) else reference.year
        month = MONTH_MAP.get(month_name, MONTH_MAP.get(month_name[:3]))
        if month:
            return datetime(year, month, 1)

    # Try just year
    year_match = PATTERNS["year_only"].search(text)
    if year_match and text.strip() == year_match.group(1):
        return datetime(int(year_match.group(1)), 1, 1)

    return None


def parse_time_filter(
    query: str,
    reference: datetime | None = None,
    default_range: Literal["day", "week", "month", "year", "all"] = "all",
) -> TimeFilter | None:
    """
    Parse a natural language time reference into a TimeFilter.

    Args:
        query: Query string potentially containing time references
        reference: Reference datetime (default: now)
        default_range: Default time range if no time reference found

    Returns:
        TimeFilter or None if no time reference found and default is "all"

    Examples:
        >>> parse_time_filter("what did I do today")
        TimeFilter(start=today 00:00, end=today 23:59)

        >>> parse_time_filter("show me January 2025")
        TimeFilter(start=2025-01-01, end=2025-01-31)

        >>> parse_time_filter("last 7 days")
        TimeFilter(start=7 days ago, end=now)
    """
    if reference is None:
        reference = datetime.now()

    query_lower = query.lower()

    # Check for "today"
    if PATTERNS["today"].search(query_lower):
        return TimeFilter(
            start=_start_of_day(reference),
            end=_end_of_day(reference),
            description="today",
        )

    # Check for "yesterday"
    if PATTERNS["yesterday"].search(query_lower):
        yesterday = reference - timedelta(days=1)
        return TimeFilter(
            start=_start_of_day(yesterday),
            end=_end_of_day(yesterday),
            description="yesterday",
        )

    # Check for "this week"
    if PATTERNS["this_week"].search(query_lower):
        return TimeFilter(
            start=_start_of_week(reference),
            end=_end_of_week(reference),
            description="this week",
        )

    # Check for "last week"
    if PATTERNS["last_week"].search(query_lower):
        last_week = reference - timedelta(weeks=1)
        return TimeFilter(
            start=_start_of_week(last_week),
            end=_end_of_week(last_week),
            description="last week",
        )

    # Check for "this month"
    if PATTERNS["this_month"].search(query_lower):
        return TimeFilter(
            start=_start_of_month(reference),
            end=_end_of_month(reference),
            description="this month",
        )

    # Check for "last month"
    if PATTERNS["last_month"].search(query_lower):
        last_month = reference.replace(day=1) - timedelta(days=1)
        return TimeFilter(
            start=_start_of_month(last_month),
            end=_end_of_month(last_month),
            description="last month",
        )

    # Check for "this year"
    if PATTERNS["this_year"].search(query_lower):
        return TimeFilter(
            start=_start_of_year(reference),
            end=_end_of_year(reference),
            description="this year",
        )

    # Check for "last year"
    if PATTERNS["last_year"].search(query_lower):
        last_year = reference.replace(year=reference.year - 1)
        return TimeFilter(
            start=_start_of_year(last_year),
            end=_end_of_year(last_year),
            description="last year",
        )

    # Check for "last [weekday]" (e.g., "last Saturday")
    match = PATTERNS["last_weekday"].search(query_lower)
    if match:
        weekday_name = match.group(1).lower()
        start, end = _resolve_last_weekday(weekday_name, reference)
        return TimeFilter(
            start=start,
            end=end,
            description=f"last {weekday_name.title()}",
        )

    # Check for "this [weekday]" (e.g., "this Monday")
    match = PATTERNS["this_weekday"].search(query_lower)
    if match:
        weekday_name = match.group(1).lower()
        start, end = _resolve_this_weekday(weekday_name, reference)
        return TimeFilter(
            start=start,
            end=end,
            description=f"this {weekday_name.title()}",
        )

    # Check for "last N days"
    match = PATTERNS["last_n_days"].search(query_lower)
    if match:
        n = int(match.group(1))
        return TimeFilter(
            start=_start_of_day(reference - timedelta(days=n)),
            end=_end_of_day(reference),
            description=f"last {n} days",
        )

    # Check for "last N weeks"
    match = PATTERNS["last_n_weeks"].search(query_lower)
    if match:
        n = int(match.group(1))
        return TimeFilter(
            start=_start_of_day(reference - timedelta(weeks=n)),
            end=_end_of_day(reference),
            description=f"last {n} weeks",
        )

    # Check for "last N months"
    match = PATTERNS["last_n_months"].search(query_lower)
    if match:
        n = int(match.group(1))
        # Approximate months as 30 days
        start = reference - timedelta(days=n * 30)
        return TimeFilter(
            start=_start_of_day(start),
            end=_end_of_day(reference),
            description=f"last {n} months",
        )

    # Check for "N days ago"
    match = PATTERNS["n_days_ago"].search(query_lower)
    if match:
        n = int(match.group(1))
        target = reference - timedelta(days=n)
        return TimeFilter(
            start=_start_of_day(target),
            end=_end_of_day(target),
            description=f"{n} days ago",
        )

    # Check for "N weeks ago"
    match = PATTERNS["n_weeks_ago"].search(query_lower)
    if match:
        n = int(match.group(1))
        target = reference - timedelta(weeks=n)
        return TimeFilter(
            start=_start_of_week(target),
            end=_end_of_week(target),
            description=f"{n} weeks ago",
        )

    # Check for quarter
    match = PATTERNS["quarter"].search(query_lower)
    if match:
        quarter = int(match.group(1)[1])
        year = int(match.group(2)) if match.group(2) else reference.year
        start, end = _get_quarter_range(quarter, year)
        return TimeFilter(
            start=start,
            end=end,
            description=f"Q{quarter} {year}",
        )

    # Check for date range (X to Y)
    match = PATTERNS["date_range"].search(query_lower)
    if match:
        start_text = match.group(1).strip()
        end_text = match.group(2).strip()

        start_date = _parse_single_date(start_text, reference)
        end_date = _parse_single_date(end_text, reference)

        if start_date and end_date:
            return TimeFilter(
                start=_start_of_day(start_date),
                end=_end_of_day(end_date),
                description=f"{start_text} to {end_text}",
            )

    # Check for between X and Y
    match = PATTERNS["between"].search(query_lower)
    if match:
        start_text = match.group(1).strip()
        end_text = match.group(2).strip()

        start_date = _parse_single_date(start_text, reference)
        end_date = _parse_single_date(end_text, reference)

        if start_date and end_date:
            return TimeFilter(
                start=_start_of_day(start_date),
                end=_end_of_day(end_date),
                description=f"between {start_text} and {end_text}",
            )

    # Check for "since X"
    match = PATTERNS["since"].search(query_lower)
    if match:
        since_text = match.group(1).strip()
        since_date = _parse_single_date(since_text, reference)

        if since_date:
            return TimeFilter(
                start=_start_of_day(since_date),
                end=_end_of_day(reference),
                description=f"since {since_text}",
            )

    # Check for "before X"
    match = PATTERNS["before"].search(query_lower)
    if match:
        before_text = match.group(1).strip()
        before_date = _parse_single_date(before_text, reference)

        if before_date:
            # Start from a reasonable past date (1 year ago)
            start = reference - timedelta(days=365)
            return TimeFilter(
                start=_start_of_day(start),
                end=_end_of_day(before_date - timedelta(days=1)),
                description=f"before {before_text}",
                confidence=0.8,
            )

    # Check for "after X"
    match = PATTERNS["after"].search(query_lower)
    if match:
        after_text = match.group(1).strip()
        after_date = _parse_single_date(after_text, reference)

        if after_date:
            return TimeFilter(
                start=_start_of_day(after_date + timedelta(days=1)),
                end=_end_of_day(reference),
                description=f"after {after_text}",
            )

    # Check for "on X"
    match = PATTERNS["on_date"].search(query_lower)
    if match:
        on_text = match.group(1).strip()
        on_date = _parse_single_date(on_text, reference)

        if on_date:
            return TimeFilter(
                start=_start_of_day(on_date),
                end=_end_of_day(on_date),
                description=f"on {on_text}",
            )

    # Check for ordinal day only (e.g., "the 25th", "on the 25th")
    match = PATTERNS["ordinal_day"].search(query_lower)
    if match:
        day = int(match.group(1))
        if 1 <= day <= 31:
            # Default to current month/year
            try:
                target_date = reference.replace(day=day)
                # If the day is in the future within this month, use previous month
                if target_date > reference:
                    # Try previous month
                    if reference.month == 1:
                        target_date = reference.replace(year=reference.year - 1, month=12, day=day)
                    else:
                        try:
                            target_date = reference.replace(month=reference.month - 1, day=day)
                        except ValueError:
                            # Day doesn't exist in previous month, keep current month
                            pass
                return TimeFilter(
                    start=_start_of_day(target_date),
                    end=_end_of_day(target_date),
                    description=f"the {day}{'st' if day == 1 else 'nd' if day == 2 else 'rd' if day == 3 else 'th'}",
                    confidence=0.9,  # Slightly lower confidence since we're inferring the month
                )
            except ValueError:
                pass  # Invalid day for the month

    # Check for "during X"
    match = PATTERNS["during"].search(query_lower)
    if match:
        during_text = match.group(1).strip()
        # Recursively parse the period
        inner_filter = parse_time_filter(during_text, reference, "all")
        if inner_filter:
            return TimeFilter(
                start=inner_filter.start,
                end=inner_filter.end,
                description=f"during {during_text}",
            )

    # Check for month year (e.g., "January 2025" or just "January")
    match = PATTERNS["month_year"].search(query_lower)
    if match:
        month_name = match.group(1).lower()
        year = int(match.group(2)) if match.group(2) else reference.year
        month = MONTH_MAP.get(month_name, MONTH_MAP.get(month_name[:3]))

        if month:
            start = _start_of_day(datetime(year, month, 1))
            end = _end_of_month(start)
            return TimeFilter(
                start=start,
                end=end,
                description=f"{month_name.title()} {year}",
            )

    # Check for just a year
    match = PATTERNS["year_only"].search(query_lower)
    if match:
        year = int(match.group(1))
        return TimeFilter(
            start=_start_of_year(datetime(year, 1, 1)),
            end=_end_of_year(datetime(year, 12, 31)),
            description=str(year),
        )

    # Check for specific date patterns
    single_date = _parse_single_date(query, reference)
    if single_date:
        return TimeFilter(
            start=_start_of_day(single_date),
            end=_end_of_day(single_date),
            description=single_date.strftime("%B %d, %Y"),
        )

    # No time reference found - return default
    if default_range == "all":
        return None
    elif default_range == "day":
        return TimeFilter(
            start=_start_of_day(reference),
            end=_end_of_day(reference),
            description="today",
            confidence=0.5,
        )
    elif default_range == "week":
        return TimeFilter(
            start=_start_of_week(reference),
            end=_end_of_week(reference),
            description="this week",
            confidence=0.5,
        )
    elif default_range == "month":
        return TimeFilter(
            start=_start_of_month(reference),
            end=_end_of_month(reference),
            description="this month",
            confidence=0.5,
        )
    elif default_range == "year":
        return TimeFilter(
            start=_start_of_year(reference),
            end=_end_of_year(reference),
            description="this year",
            confidence=0.5,
        )

    return None


def parse_time_filter_with_ambiguity(
    query: str,
    reference: datetime | None = None,
) -> TimeParseResult | None:
    """
    Parse a time reference with ambiguity detection.

    This function checks for potentially ambiguous time expressions like
    "last July" (which year?) and returns clarification options.

    Args:
        query: Query string potentially containing time references
        reference: Reference datetime (default: now)

    Returns:
        TimeParseResult with ambiguity information, or None if no time reference found

    Examples:
        >>> result = parse_time_filter_with_ambiguity("last July")  # in January 2026
        >>> result.ambiguous
        True
        >>> result.clarification_options
        ['July 2025', 'July 2024']
    """
    if reference is None:
        reference = datetime.now()

    query_lower = query.lower()

    # Check for "last [month name]" - potentially ambiguous
    match = PATTERNS["last_month_name"].search(query_lower)
    if match:
        month_name = match.group(1)
        return _resolve_month_reference(month_name, reference, is_last=True)

    # For all other cases, use the regular parser and wrap in TimeParseResult
    time_filter = parse_time_filter(query, reference, "all")

    if time_filter is None:
        return None

    return TimeParseResult(
        time_filter=time_filter,
        confidence=time_filter.confidence,
        ambiguous=False,
        raw_expression=time_filter.description,
    )


def extract_time_references(query: str) -> list[str]:
    """
    Extract potential time references from a query.

    Args:
        query: Query string

    Returns:
        List of potential time reference strings found
    """
    references = []

    for _pattern_name, pattern in PATTERNS.items():
        matches = pattern.findall(query)
        if matches:
            for match in matches:
                if isinstance(match, tuple):
                    references.append(" ".join(str(m) for m in match if m))
                else:
                    references.append(str(match))

    return list(set(references))


if __name__ == "__main__":
    import fire

    def parse(query: str, reference: str | None = None):
        """
        Parse a time filter from a query string.

        Args:
            query: Query to parse
            reference: Optional reference date (ISO format)
        """
        ref = datetime.fromisoformat(reference) if reference else None
        result = parse_time_filter(query, ref)

        if result:
            return result.to_dict()
        return {"error": "No time reference found"}

    def extract(query: str):
        """Extract time references from a query."""
        return extract_time_references(query)

    def demo():
        """Run demo with various time expressions."""
        examples = [
            "what did I do today",
            "show me yesterday's activities",
            "this week",
            "last month",
            "January 2025",
            "Q1 2025",
            "last 7 days",
            "3 days ago",
            "from Jan 1 to Jan 15",
            "since December 2024",
            "on January 15, 2025",
            "during this week",
            "between Jan 1 and Jan 31",
            "2024",
            # New weekday patterns
            "last Saturday",
            "this Monday",
            "what did I do last Friday",
        ]

        results = []
        for example in examples:
            result = parse_time_filter(example)
            results.append(
                {
                    "query": example,
                    "parsed": result.to_dict() if result else None,
                }
            )

        return results

    def demo_ambiguity():
        """Run demo showing ambiguity detection."""
        # Simulate being in January 2026
        reference = datetime(2026, 1, 27)

        examples = [
            "last July",
            "last December",
            "last March",
            "July 2025",  # Not ambiguous - year specified
        ]

        results = []
        for example in examples:
            result = parse_time_filter_with_ambiguity(example, reference)
            results.append(
                {
                    "query": example,
                    "reference": reference.isoformat(),
                    "result": result.to_dict() if result else None,
                }
            )

        return results

    fire.Fire({"parse": parse, "extract": extract, "demo": demo, "demo_ambiguity": demo_ambiguity})
