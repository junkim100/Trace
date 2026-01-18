"""
Aggregates Computation for Trace Daily Revision

Computes daily rollups for "most" queries (most watched, most listened, etc.)
and stores them in the aggregates table.

P6-07: Aggregates computation
"""

import json
import logging
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

from src.core.paths import DB_PATH
from src.db.migrations import get_connection
from src.revise.schemas import DailyRevisionSchema

logger = logging.getLogger(__name__)

# Aggregate key types
KEY_TYPES = {"category", "entity", "co_activity", "app", "domain", "topic", "media"}


@dataclass
class AggregateItem:
    """A single aggregate item."""

    key_type: str
    key: str
    value_num: float  # Duration in minutes or count
    extra: dict | None = None


@dataclass
class AggregatesResult:
    """Result of computing aggregates."""

    period_type: str
    period_start: str
    period_end: str
    total_aggregates: int
    aggregates: list[AggregateItem]


class AggregatesComputer:
    """
    Computes and stores daily aggregates for analytics queries.

    Aggregates include:
    - Time per category (work, learning, entertainment, etc.)
    - Time per app
    - Time per domain
    - Time per topic
    - Media consumption time
    - Co-activity patterns
    """

    def __init__(self, db_path: Path | str | None = None):
        """
        Initialize the computer.

        Args:
            db_path: Path to SQLite database
        """
        self.db_path = Path(db_path) if db_path else DB_PATH

    def compute_daily_aggregates(
        self,
        day: datetime,
        revision: DailyRevisionSchema | None = None,
    ) -> AggregatesResult:
        """
        Compute daily aggregates from hourly notes and/or revision data.

        Args:
            day: The day to compute aggregates for
            revision: Optional DailyRevisionSchema with pre-computed top entities

        Returns:
            AggregatesResult with computed aggregates
        """
        aggregates = []

        conn = get_connection(self.db_path)
        try:
            # Get all hourly notes for the day
            hourly_notes = self._get_hourly_notes(conn, day)

            # Compute category aggregates from hourly notes
            category_aggs = self._compute_category_aggregates(hourly_notes)
            aggregates.extend(category_aggs)

            # Compute app aggregates
            app_aggs = self._compute_app_aggregates(hourly_notes)
            aggregates.extend(app_aggs)

            # Compute domain aggregates
            domain_aggs = self._compute_domain_aggregates(hourly_notes)
            aggregates.extend(domain_aggs)

            # Compute topic aggregates
            topic_aggs = self._compute_topic_aggregates(hourly_notes)
            aggregates.extend(topic_aggs)

            # Compute media aggregates
            media_aggs = self._compute_media_aggregates(hourly_notes)
            aggregates.extend(media_aggs)

            # If revision data is provided, use its top entities as well
            if revision:
                # Add pre-computed aggregates from revision
                revision_aggs = self._extract_revision_aggregates(revision)
                aggregates.extend(revision_aggs)

            # Store aggregates in database
            day_start = day.replace(hour=0, minute=0, second=0, microsecond=0)
            day_end = day.replace(hour=23, minute=59, second=59)

            self._store_aggregates(conn, "day", day_start, day_end, aggregates)

            conn.commit()

        finally:
            conn.close()

        return AggregatesResult(
            period_type="day",
            period_start=day.strftime("%Y-%m-%d"),
            period_end=day.strftime("%Y-%m-%d"),
            total_aggregates=len(aggregates),
            aggregates=aggregates,
        )

    def _get_hourly_notes(
        self,
        conn,
        day: datetime,
    ) -> list[dict]:
        """Get all hourly notes for a day."""
        cursor = conn.cursor()

        day_start = day.replace(hour=0, minute=0, second=0, microsecond=0)
        day_end = day.replace(hour=23, minute=59, second=59, microsecond=999999)

        cursor.execute(
            """
            SELECT note_id, start_ts, end_ts, json_payload
            FROM notes
            WHERE note_type = 'hour'
            AND start_ts >= ? AND start_ts <= ?
            ORDER BY start_ts
            """,
            (day_start.isoformat(), day_end.isoformat()),
        )

        notes = []
        for row in cursor.fetchall():
            notes.append(
                {
                    "note_id": row["note_id"],
                    "start_ts": datetime.fromisoformat(row["start_ts"]),
                    "end_ts": datetime.fromisoformat(row["end_ts"]),
                    "payload": json.loads(row["json_payload"]),
                }
            )

        return notes

    def _compute_category_aggregates(
        self,
        hourly_notes: list[dict],
    ) -> list[AggregateItem]:
        """Compute time per activity category."""
        category_minutes = {}

        for note in hourly_notes:
            payload = note["payload"]
            activities = payload.get("activities", [])

            for activity in activities:
                category = activity.get("category", "other")
                time_start = activity.get("time_start", "")
                time_end = activity.get("time_end", "")

                # Parse times and calculate duration
                duration = self._calculate_duration(time_start, time_end)
                category_minutes[category] = category_minutes.get(category, 0) + duration

        return [
            AggregateItem(key_type="category", key=cat, value_num=mins)
            for cat, mins in sorted(category_minutes.items(), key=lambda x: -x[1])
        ]

    def _compute_app_aggregates(
        self,
        hourly_notes: list[dict],
    ) -> list[AggregateItem]:
        """Compute time per application."""
        app_minutes = {}

        for note in hourly_notes:
            payload = note["payload"]
            activities = payload.get("activities", [])

            for activity in activities:
                app = activity.get("app")
                if not app:
                    continue

                time_start = activity.get("time_start", "")
                time_end = activity.get("time_end", "")

                duration = self._calculate_duration(time_start, time_end)
                app_minutes[app] = app_minutes.get(app, 0) + duration

        return [
            AggregateItem(key_type="app", key=app, value_num=mins)
            for app, mins in sorted(app_minutes.items(), key=lambda x: -x[1])[:20]
        ]

    def _compute_domain_aggregates(
        self,
        hourly_notes: list[dict],
    ) -> list[AggregateItem]:
        """Compute visits per domain."""
        domain_count = {}

        for note in hourly_notes:
            payload = note["payload"]
            websites = payload.get("websites", [])

            for site in websites:
                domain = site.get("domain")
                if domain:
                    domain_count[domain] = domain_count.get(domain, 0) + 1

        # For domains, use count as value (no duration available)
        return [
            AggregateItem(key_type="domain", key=domain, value_num=count)
            for domain, count in sorted(domain_count.items(), key=lambda x: -x[1])[:20]
        ]

    def _compute_topic_aggregates(
        self,
        hourly_notes: list[dict],
    ) -> list[AggregateItem]:
        """Compute engagement per topic."""
        topic_score = {}

        for note in hourly_notes:
            payload = note["payload"]
            topics = payload.get("topics", [])

            for topic in topics:
                name = topic.get("name", "")
                confidence = topic.get("confidence", 0.5)
                if name:
                    # Score = confidence (assuming 1 hour engagement per note)
                    topic_score[name] = topic_score.get(name, 0) + (confidence * 60)

        return [
            AggregateItem(key_type="topic", key=topic, value_num=score)
            for topic, score in sorted(topic_score.items(), key=lambda x: -x[1])[:20]
        ]

    def _compute_media_aggregates(
        self,
        hourly_notes: list[dict],
    ) -> list[AggregateItem]:
        """Compute media consumption time."""
        media_minutes = {}

        for note in hourly_notes:
            payload = note["payload"]
            media = payload.get("media", {})

            # Listening
            for item in media.get("listening", []):
                artist = item.get("artist", "")
                track = item.get("track", "")
                duration = item.get("duration_seconds", 0) / 60

                key = f"{artist} - {track}"
                media_minutes[key] = media_minutes.get(key, 0) + duration

            # Watching
            for item in media.get("watching", []):
                title = item.get("title", "")
                duration = item.get("duration_seconds", 0) / 60

                media_minutes[title] = media_minutes.get(title, 0) + duration

        return [
            AggregateItem(
                key_type="media",
                key=media,
                value_num=mins,
                extra={"type": "track" if " - " in media else "video"},
            )
            for media, mins in sorted(media_minutes.items(), key=lambda x: -x[1])[:20]
        ]

    def _extract_revision_aggregates(
        self,
        revision: DailyRevisionSchema,
    ) -> list[AggregateItem]:
        """Extract aggregates from revision's top_entities."""
        aggregates = []
        top = revision.top_entities

        # Topics from revision (with minutes)
        for item in top.topics:
            aggregates.append(
                AggregateItem(
                    key_type="topic",
                    key=item.name,
                    value_num=item.total_minutes,
                    extra={"source": "revision"},
                )
            )

        # Apps from revision
        for item in top.apps:
            aggregates.append(
                AggregateItem(
                    key_type="app",
                    key=item.name,
                    value_num=item.total_minutes,
                    extra={"source": "revision"},
                )
            )

        # Domains from revision
        for item in top.domains:
            aggregates.append(
                AggregateItem(
                    key_type="domain",
                    key=item.name,
                    value_num=item.total_minutes,
                    extra={"source": "revision"},
                )
            )

        # Media from revision
        for item in top.media:
            aggregates.append(
                AggregateItem(
                    key_type="media",
                    key=item.name,
                    value_num=item.total_minutes,
                    extra={"type": item.type, "source": "revision"},
                )
            )

        return aggregates

    def _calculate_duration(self, time_start: str, time_end: str) -> float:
        """
        Calculate duration in minutes from HH:MM strings.

        Args:
            time_start: Start time in HH:MM format
            time_end: End time in HH:MM format

        Returns:
            Duration in minutes
        """
        try:
            start_parts = time_start.split(":")
            end_parts = time_end.split(":")

            start_mins = int(start_parts[0]) * 60 + int(start_parts[1])
            end_mins = int(end_parts[0]) * 60 + int(end_parts[1])

            # Handle midnight crossing
            if end_mins < start_mins:
                end_mins += 24 * 60

            return end_mins - start_mins

        except (ValueError, IndexError):
            return 0

    def _store_aggregates(
        self,
        conn,
        period_type: str,
        period_start: datetime,
        period_end: datetime,
        aggregates: list[AggregateItem],
    ) -> None:
        """Store aggregates in database."""
        cursor = conn.cursor()

        # Delete existing aggregates for this period
        cursor.execute(
            """
            DELETE FROM aggregates
            WHERE period_type = ? AND period_start_ts = ?
            """,
            (period_type, period_start.isoformat()),
        )

        # Insert new aggregates
        for agg in aggregates:
            agg_id = str(uuid.uuid4())
            cursor.execute(
                """
                INSERT INTO aggregates
                (agg_id, period_type, period_start_ts, period_end_ts, key_type, key, value_num, extra_json, created_ts, updated_ts)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    agg_id,
                    period_type,
                    period_start.isoformat(),
                    period_end.isoformat(),
                    agg.key_type,
                    agg.key,
                    agg.value_num,
                    json.dumps(agg.extra) if agg.extra else None,
                    datetime.now().isoformat(),
                    datetime.now().isoformat(),
                ),
            )

        logger.info(
            f"Stored {len(aggregates)} aggregates for {period_type} {period_start.strftime('%Y-%m-%d')}"
        )

    def get_aggregates_for_day(
        self,
        day: datetime,
        key_type: str | None = None,
    ) -> list[AggregateItem]:
        """
        Get aggregates for a specific day.

        Args:
            day: The day to get aggregates for
            key_type: Optional filter by key type

        Returns:
            List of AggregateItem
        """
        conn = get_connection(self.db_path)
        try:
            cursor = conn.cursor()

            day_start = day.replace(hour=0, minute=0, second=0, microsecond=0)

            if key_type:
                cursor.execute(
                    """
                    SELECT key_type, key, value_num, extra_json
                    FROM aggregates
                    WHERE period_type = 'day' AND period_start_ts = ? AND key_type = ?
                    ORDER BY value_num DESC
                    """,
                    (day_start.isoformat(), key_type),
                )
            else:
                cursor.execute(
                    """
                    SELECT key_type, key, value_num, extra_json
                    FROM aggregates
                    WHERE period_type = 'day' AND period_start_ts = ?
                    ORDER BY key_type, value_num DESC
                    """,
                    (day_start.isoformat(),),
                )

            aggregates = []
            for row in cursor.fetchall():
                aggregates.append(
                    AggregateItem(
                        key_type=row["key_type"],
                        key=row["key"],
                        value_num=row["value_num"],
                        extra=json.loads(row["extra_json"]) if row["extra_json"] else None,
                    )
                )

            return aggregates

        finally:
            conn.close()

    def get_top_for_period(
        self,
        key_type: str,
        start_date: datetime,
        end_date: datetime,
        limit: int = 10,
    ) -> list[AggregateItem]:
        """
        Get top items of a type across a date range.

        Args:
            key_type: Type to query (app, topic, domain, media)
            start_date: Start of period
            end_date: End of period
            limit: Maximum results

        Returns:
            List of AggregateItem sorted by total value
        """
        conn = get_connection(self.db_path)
        try:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT key, SUM(value_num) as total
                FROM aggregates
                WHERE period_type = 'day'
                AND key_type = ?
                AND period_start_ts >= ? AND period_start_ts <= ?
                GROUP BY key
                ORDER BY total DESC
                LIMIT ?
                """,
                (
                    key_type,
                    start_date.isoformat(),
                    end_date.isoformat(),
                    limit,
                ),
            )

            return [
                AggregateItem(key_type=key_type, key=row["key"], value_num=row["total"])
                for row in cursor.fetchall()
            ]

        finally:
            conn.close()


if __name__ == "__main__":
    import fire

    def compute(day: str | None = None, db_path: str | None = None):
        """
        Compute daily aggregates.

        Args:
            day: Date in YYYY-MM-DD format (defaults to today)
            db_path: Path to database
        """
        if day:
            target_day = datetime.strptime(day, "%Y-%m-%d")
        else:
            target_day = datetime.now()

        computer = AggregatesComputer(db_path=db_path)
        result = computer.compute_daily_aggregates(target_day)

        return {
            "day": result.period_start,
            "total_aggregates": result.total_aggregates,
            "by_type": {
                kt: len([a for a in result.aggregates if a.key_type == kt]) for kt in KEY_TYPES
            },
        }

    def get(
        day: str | None = None,
        key_type: str | None = None,
        db_path: str | None = None,
    ):
        """
        Get aggregates for a day.

        Args:
            day: Date in YYYY-MM-DD format (defaults to today)
            key_type: Optional filter (app, topic, domain, media, category)
            db_path: Path to database
        """
        if day:
            target_day = datetime.strptime(day, "%Y-%m-%d")
        else:
            target_day = datetime.now()

        computer = AggregatesComputer(db_path=db_path)
        aggregates = computer.get_aggregates_for_day(target_day, key_type)

        return [
            {
                "type": a.key_type,
                "key": a.key,
                "value": f"{a.value_num:.1f}",
            }
            for a in aggregates[:20]
        ]

    def top(
        key_type: str,
        days: int = 7,
        limit: int = 10,
        db_path: str | None = None,
    ):
        """
        Get top items across a date range.

        Args:
            key_type: Type to query (app, topic, domain, media)
            days: Number of days to look back
            limit: Maximum results
            db_path: Path to database
        """
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days)

        computer = AggregatesComputer(db_path=db_path)
        aggregates = computer.get_top_for_period(key_type, start_date, end_date, limit)

        return [{"key": a.key, "total": f"{a.value_num:.1f}"} for a in aggregates]

    fire.Fire(
        {
            "compute": compute,
            "get": get,
            "top": top,
        }
    )
