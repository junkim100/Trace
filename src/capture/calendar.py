"""
Calendar Event Capture for Trace

Captures calendar events from macOS Calendar.app using EventKit framework.
Events are used to add context to hourly notes (e.g., "During meeting with X").

P14-01: Calendar integration
"""

import json
import logging
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

# Cache interval - don't query calendar more often than this
CALENDAR_CACHE_INTERVAL_SECONDS = 300  # 5 minutes


@dataclass
class CalendarEvent:
    """A calendar event."""

    event_id: str
    title: str
    start_time: datetime
    end_time: datetime
    location: str | None
    attendees: list[str] | None
    is_all_day: bool
    calendar_name: str | None

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "event_id": self.event_id,
            "title": self.title,
            "start_time": self.start_time.isoformat(),
            "end_time": self.end_time.isoformat(),
            "location": self.location,
            "attendees": self.attendees,
            "is_all_day": self.is_all_day,
            "calendar_name": self.calendar_name,
        }

    def to_json(self) -> str:
        """Serialize to JSON string."""
        return json.dumps(self.to_dict())

    @classmethod
    def from_dict(cls, data: dict) -> "CalendarEvent":
        """Create from dictionary."""
        return cls(
            event_id=data["event_id"],
            title=data["title"],
            start_time=datetime.fromisoformat(data["start_time"]),
            end_time=datetime.fromisoformat(data["end_time"]),
            location=data.get("location"),
            attendees=data.get("attendees"),
            is_all_day=data.get("is_all_day", False),
            calendar_name=data.get("calendar_name"),
        )


def _get_calendar_events_applescript(
    start_time: datetime,
    end_time: datetime,
) -> list[CalendarEvent]:
    """
    Get calendar events using AppleScript.

    This queries Calendar.app for events in the specified time range.
    """
    if sys.platform != "darwin":
        return []

    # Format dates for AppleScript
    start_str = start_time.strftime("%Y-%m-%d %H:%M:%S")
    end_str = end_time.strftime("%Y-%m-%d %H:%M:%S")

    script = f"""
    tell application "Calendar"
        set outputList to {{}}
        set startDate to date "{start_str}"
        set endDate to date "{end_str}"

        repeat with cal in calendars
            set calName to name of cal
            set calEvents to (every event of cal whose start date >= startDate and start date < endDate)

            repeat with evt in calEvents
                try
                    set evtId to uid of evt
                    set evtTitle to summary of evt
                    set evtStart to start date of evt
                    set evtEnd to end date of evt
                    set evtLoc to ""
                    try
                        set evtLoc to location of evt
                    end try
                    set isAllDay to allday event of evt

                    -- Get attendees
                    set attendeeList to {{}}
                    try
                        repeat with att in attendees of evt
                            set end of attendeeList to display name of att
                        end repeat
                    end try

                    -- Format: ID|||Title|||Start|||End|||Location|||AllDay|||Calendar|||Attendees
                    set evtStartStr to (year of evtStart as string) & "-" & text -2 thru -1 of ("0" & (month of evtStart as number) as string) & "-" & text -2 thru -1 of ("0" & (day of evtStart) as string) & "T" & text -2 thru -1 of ("0" & (hours of evtStart) as string) & ":" & text -2 thru -1 of ("0" & (minutes of evtStart) as string) & ":00"
                    set evtEndStr to (year of evtEnd as string) & "-" & text -2 thru -1 of ("0" & (month of evtEnd as number) as string) & "-" & text -2 thru -1 of ("0" & (day of evtEnd) as string) & "T" & text -2 thru -1 of ("0" & (hours of evtEnd) as string) & ":" & text -2 thru -1 of ("0" & (minutes of evtEnd) as string) & ":00"

                    set attendeeStr to ""
                    if (count of attendeeList) > 0 then
                        set AppleScript's text item delimiters to ","
                        set attendeeStr to attendeeList as string
                        set AppleScript's text item delimiters to ""
                    end if

                    set end of outputList to evtId & "|||" & evtTitle & "|||" & evtStartStr & "|||" & evtEndStr & "|||" & evtLoc & "|||" & (isAllDay as string) & "|||" & calName & "|||" & attendeeStr
                end try
            end repeat
        end repeat

        set AppleScript's text item delimiters to "\\n"
        set outputStr to outputList as string
        set AppleScript's text item delimiters to ""
        return outputStr
    end tell
    """

    try:
        result = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True,
            text=True,
            timeout=10,  # Reduced from 30s for faster failure
        )

        if result.returncode != 0:
            if "not allowed" in result.stderr.lower() or "access" in result.stderr.lower():
                logger.warning(
                    "Calendar access not granted. Please allow Calendar access in System Settings."
                )
            else:
                logger.debug(f"Calendar AppleScript failed: {result.stderr}")
            return []

        events = []
        for line in result.stdout.strip().split("\n"):
            if not line or "|||" not in line:
                continue

            parts = line.split("|||")
            if len(parts) < 7:
                continue

            try:
                event_id = parts[0]
                title = parts[1]
                start_str = parts[2]
                end_str = parts[3]
                location = parts[4] if parts[4] else None
                is_all_day = parts[5].lower() == "true"
                calendar_name = parts[6] if parts[6] else None
                attendees = parts[7].split(",") if len(parts) > 7 and parts[7] else None

                events.append(
                    CalendarEvent(
                        event_id=event_id,
                        title=title,
                        start_time=datetime.fromisoformat(start_str),
                        end_time=datetime.fromisoformat(end_str),
                        location=location,
                        attendees=attendees,
                        is_all_day=is_all_day,
                        calendar_name=calendar_name,
                    )
                )
            except (ValueError, IndexError) as e:
                logger.debug(f"Failed to parse calendar event: {e}")
                continue

        return events

    except subprocess.TimeoutExpired:
        logger.warning("Calendar query timed out")
        return []
    except Exception as e:
        logger.error(f"Failed to get calendar events: {e}")
        return []


class CalendarCapture:
    """
    Captures calendar events from macOS Calendar.app.

    Provides caching to avoid excessive Calendar queries.
    """

    def __init__(self, cache_interval: float = CALENDAR_CACHE_INTERVAL_SECONDS):
        """
        Initialize the calendar capturer.

        Args:
            cache_interval: Minimum seconds between calendar queries
        """
        self.cache_interval = cache_interval
        self._cached_events: list[CalendarEvent] = []
        self._cache_start: datetime | None = None
        self._cache_end: datetime | None = None
        self._last_query_time: datetime | None = None
        self._permission_checked: bool = False
        self._has_permission: bool = False

    def get_events_for_hour(self, hour_start: datetime) -> list[CalendarEvent]:
        """
        Get calendar events that overlap with a specific hour.

        Args:
            hour_start: Start of the hour

        Returns:
            List of CalendarEvent objects
        """
        hour_end = hour_start + timedelta(hours=1)
        return self.get_events_in_range(hour_start, hour_end)

    def get_events_in_range(
        self,
        start_time: datetime,
        end_time: datetime,
    ) -> list[CalendarEvent]:
        """
        Get calendar events in a time range.

        Uses caching to avoid excessive queries.

        Args:
            start_time: Start of the range
            end_time: End of the range

        Returns:
            List of CalendarEvent objects
        """
        # Check permission on first use
        if not self._permission_checked:
            self._permission_checked = True
            self._has_permission = check_calendar_permission()
            if not self._has_permission:
                logger.debug(
                    "Calendar permission not available. "
                    "Enable in System Settings → Privacy & Security → Automation → Trace → Calendar"
                )

        # Skip if no permission
        if not self._has_permission:
            return []

        now = datetime.now()

        # Check if we can use cached data
        if (
            self._cached_events
            and self._cache_start
            and self._cache_end
            and self._last_query_time
            and (now - self._last_query_time).total_seconds() < self.cache_interval
            and start_time >= self._cache_start
            and end_time <= self._cache_end
        ):
            # Filter cached events for the requested range
            return [
                e
                for e in self._cached_events
                if e.start_time < end_time and e.end_time > start_time
            ]

        # Query calendar for a wider range (cache for the whole day)
        query_start = start_time.replace(hour=0, minute=0, second=0, microsecond=0)
        query_end = query_start + timedelta(days=1)

        events = _get_calendar_events_applescript(query_start, query_end)

        # Update cache
        self._cached_events = events
        self._cache_start = query_start
        self._cache_end = query_end
        self._last_query_time = now

        # Filter for the requested range
        return [e for e in events if e.start_time < end_time and e.end_time > start_time]

    def get_current_event(self) -> CalendarEvent | None:
        """
        Get the currently active calendar event (if any).

        Returns:
            CalendarEvent if currently in an event, None otherwise
        """
        now = datetime.now()
        events = self.get_events_in_range(now - timedelta(hours=1), now + timedelta(hours=1))

        for event in events:
            if event.start_time <= now <= event.end_time:
                return event

        return None

    def clear_cache(self) -> None:
        """Clear the cached events."""
        self._cached_events = []
        self._cache_start = None
        self._cache_end = None
        self._last_query_time = None


def check_calendar_permission() -> bool:
    """
    Check if calendar access is granted.

    Returns:
        True if calendar access is available
    """
    if sys.platform != "darwin":
        return False

    # Try to query calendar - if it fails with permission error, access is not granted
    try:
        script = """
        tell application "Calendar"
            return count of calendars
        end tell
        """
        result = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True,
            text=True,
            timeout=5,
        )

        if result.returncode != 0:
            return False

        return True

    except Exception:
        return False


def request_calendar_permission() -> bool:
    """
    Attempt to trigger the calendar automation permission dialog.

    For unsigned apps, this may not show a dialog but will add the app
    to System Settings → Automation where the user can manually enable it.

    Returns:
        True if permission was granted, False otherwise
    """
    if sys.platform != "darwin":
        return False

    # This simple query should trigger the permission prompt
    # For unsigned apps, it adds the app to Automation settings
    try:
        script = """
        tell application "Calendar"
            return name of first calendar
        end tell
        """
        result = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True,
            text=True,
            timeout=10,
        )

        if result.returncode == 0:
            logger.info("Calendar automation permission granted")
            return True
        else:
            logger.warning(
                "Calendar permission not granted. "
                "Please enable in System Settings → Privacy & Security → Automation → Trace → Calendar"
            )
            return False

    except Exception as e:
        logger.error(f"Failed to request calendar permission: {e}")
        return False


if __name__ == "__main__":
    import fire

    def capture(hours_ahead: int = 24):
        """Capture calendar events for the next N hours."""
        capturer = CalendarCapture()
        now = datetime.now()
        events = capturer.get_events_in_range(now, now + timedelta(hours=hours_ahead))
        return [e.to_dict() for e in events]

    def current():
        """Get the current calendar event."""
        capturer = CalendarCapture()
        event = capturer.get_current_event()
        if event:
            return event.to_dict()
        return {"status": "no_current_event"}

    def check():
        """Check calendar permission."""
        return {"granted": check_calendar_permission()}

    def hour(hour: str | None = None):
        """Get events for a specific hour."""
        capturer = CalendarCapture()
        if hour:
            hour_start = datetime.fromisoformat(hour)
        else:
            hour_start = datetime.now().replace(minute=0, second=0, microsecond=0)
        events = capturer.get_events_for_hour(hour_start)
        return [e.to_dict() for e in events]

    def request():
        """Request calendar permission (triggers automation dialog)."""
        return {"granted": request_calendar_permission()}

    fire.Fire(
        {
            "capture": capture,
            "current": current,
            "check": check,
            "hour": hour,
            "request": request,
        }
    )
