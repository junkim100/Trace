"""
Hourly Summarizer Orchestrator for Trace

Coordinates the complete hourly summarization pipeline:
1. Gather evidence (events, screenshots, text buffers)
2. Triage and select keyframes
3. Call vision LLM for summarization
4. Validate JSON output
5. Render Markdown note
6. Extract and store entities
7. Compute and store embedding
8. Update database

P5-10: Hourly job executor (main orchestrator)
"""

import json
import logging
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

from openai import OpenAI

from src.core.paths import (
    DB_PATH,
    delete_hourly_screenshot_dir,
    ensure_note_directory,
    get_note_path,
)
from src.db.migrations import get_connection
from src.summarize.embeddings import EmbeddingComputer
from src.summarize.enrichment import WebEnricher
from src.summarize.entities import EntityExtractor
from src.summarize.evidence import EvidenceAggregator, HourlyEvidence
from src.summarize.keyframes import KeyframeSelector, ScreenshotCandidate, SelectedKeyframe
from src.summarize.prompts.hourly import (
    HOURLY_MODEL,
    build_vision_messages,
)
from src.summarize.render import MarkdownRenderer
from src.summarize.schemas import (
    HourlySummarySchema,
    generate_empty_summary,
    validate_with_retry,
)
from src.summarize.triage import FrameTriager, HeuristicTriager

logger = logging.getLogger(__name__)

# Maximum keyframes to include in LLM call (token budget)
MAX_KEYFRAMES_FOR_LLM = 10

# Use heuristic triage by default (set to False to use vision API for triage)
USE_HEURISTIC_TRIAGE = True


@dataclass
class SummarizationResult:
    """Result of hourly summarization."""

    success: bool
    note_id: str | None
    file_path: Path | None
    error: str | None = None

    # Statistics
    events_count: int = 0
    screenshots_count: int = 0
    keyframes_count: int = 0
    entities_count: int = 0
    embedding_computed: bool = False

    # Idle detection
    skipped_idle: bool = False
    idle_reason: str | None = None


class HourlySummarizer:
    """
    Orchestrates the complete hourly summarization pipeline.

    This is the main entry point for generating hourly notes from
    captured activity data.
    """

    def __init__(
        self,
        api_key: str | None = None,
        db_path: Path | str | None = None,
        model: str = HOURLY_MODEL,
        use_heuristic_triage: bool = USE_HEURISTIC_TRIAGE,
    ):
        """
        Initialize the hourly summarizer.

        Args:
            api_key: OpenAI API key
            db_path: Path to SQLite database
            model: Model to use for summarization
            use_heuristic_triage: Use heuristic triage instead of vision API
        """
        self.db_path = Path(db_path) if db_path else DB_PATH
        self.model = model
        self.use_heuristic_triage = use_heuristic_triage
        self._api_key = api_key
        self._client: OpenAI | None = None

        # Initialize components
        self.aggregator = EvidenceAggregator(db_path=self.db_path)
        self.keyframe_selector = KeyframeSelector()
        self.renderer = MarkdownRenderer()
        self.entity_extractor = EntityExtractor(db_path=self.db_path)
        self.embedding_computer = EmbeddingComputer(api_key=api_key, db_path=self.db_path)

        if use_heuristic_triage:
            self.triager: FrameTriager | HeuristicTriager = HeuristicTriager()
        else:
            self.triager = FrameTriager(api_key=api_key)

        # Web enricher for adding context to notes
        self.enricher = WebEnricher(api_key=api_key)

    def _get_client(self) -> OpenAI:
        """Get or create the OpenAI client."""
        if self._client is None:
            self._client = OpenAI(api_key=self._api_key) if self._api_key else OpenAI()
        return self._client

    def summarize_hour(
        self,
        hour_start: datetime,
        force: bool = False,
    ) -> SummarizationResult:
        """
        Generate an hourly summary for a specific hour.

        Args:
            hour_start: Start of the hour to summarize
            force: If True, regenerate even if note exists

        Returns:
            SummarizationResult with status and statistics
        """
        # Normalize to hour boundary
        hour_start = hour_start.replace(minute=0, second=0, microsecond=0)
        hour_end = hour_start + timedelta(hours=1)

        logger.info(f"Starting summarization for {hour_start.isoformat()}")

        # Check for existing note
        if not force:
            existing = self._check_existing_note(hour_start)
            if existing:
                logger.info(f"Note already exists for {hour_start.isoformat()}")
                return SummarizationResult(
                    success=True,
                    note_id=existing,
                    file_path=get_note_path(hour_start),
                    error=None,
                )

        # Step 1: Aggregate evidence
        logger.debug("Aggregating evidence...")
        evidence = self.aggregator.aggregate(hour_start)

        # Check if there's any activity - skip note creation if no events AND no screenshots
        # Note: Events may be 0 if user stayed in same context (no app/window switches)
        # but screenshots capture activity, so we should still create notes
        if evidence.total_events == 0 and evidence.total_screenshots == 0:
            logger.info(f"No activity for {hour_start.isoformat()}, skipping note creation")
            return SummarizationResult(
                success=True,
                note_id=None,
                file_path=None,
                error=None,
                events_count=0,
                screenshots_count=0,
            )

        # Step 2: Get screenshots and triage
        logger.debug("Selecting keyframes...")
        keyframes = self._select_keyframes(hour_start, hour_end, evidence)

        # Step 3: Call LLM for summarization (with automatic retry on empty content)
        logger.debug("Calling LLM for summarization...")
        summary = self._call_llm_with_retry(evidence, keyframes)

        if summary is None:
            logger.error("LLM summarization failed")
            return SummarizationResult(
                success=False,
                note_id=None,
                file_path=None,
                error="LLM summarization failed",
                events_count=evidence.total_events,
                screenshots_count=evidence.total_screenshots,
            )

        # Step 3b: Use LLM to verify if note has meaningful content worth keeping
        if not force:
            quality_check = self._verify_note_quality(summary, evidence)
            if not quality_check["should_keep"]:
                logger.info(
                    f"LLM determined note not worth keeping for {hour_start.isoformat()}: "
                    f"{quality_check['reason']}"
                )
                # CRITICAL: Do NOT delete screenshots here!
                # Screenshots should only be deleted after a note is successfully saved.
                logger.warning(
                    f"Skipping hour {hour_start.isoformat()} - "
                    f"screenshots preserved for potential reprocessing"
                )
                return SummarizationResult(
                    success=True,
                    note_id=None,
                    file_path=None,
                    error=None,
                    events_count=evidence.total_events,
                    screenshots_count=evidence.total_screenshots,
                    keyframes_count=len(keyframes),
                    skipped_idle=True,
                    idle_reason=quality_check["reason"],
                )

        # Step 3d: Check if LLM detected idle/AFK - skip note creation if so
        # ONLY skip if LLM explicitly sets is_idle=true to avoid losing real activity
        # Unless force=True, in which case create the note anyway
        if summary.is_idle and not force:
            idle_reason = summary.idle_reason or "User detected as idle/AFK"
            logger.info(f"Idle detected for {hour_start.isoformat()}: {idle_reason}")

            # CRITICAL: Do NOT delete screenshots here!
            # Screenshots should only be deleted after a note is successfully saved.
            # If we delete now, the data is lost forever with no way to recover or reprocess.
            # The screenshots will be cleaned up by daily revision after the day is complete.
            logger.warning(
                f"Skipping hour {hour_start.isoformat()} due to idle detection - "
                f"screenshots preserved for potential reprocessing"
            )

            return SummarizationResult(
                success=True,
                note_id=None,
                file_path=None,
                error=None,
                events_count=evidence.total_events,
                screenshots_count=evidence.total_screenshots,
                keyframes_count=len(keyframes),
                skipped_idle=True,
                idle_reason=idle_reason,
            )
        elif summary.is_idle and force:
            logger.info("Idle detected but force=True, creating note anyway")

        # Step 3e: Final content validation - catch empty notes that slipped through
        # This check runs even when force=True to prevent saving useless notes
        if not self._has_meaningful_content(summary):
            logger.warning(
                f"Note has no meaningful content for {hour_start.isoformat()}, "
                "skipping save and preserving screenshots"
            )
            return SummarizationResult(
                success=True,
                note_id=None,
                file_path=None,
                error=None,
                events_count=evidence.total_events,
                screenshots_count=evidence.total_screenshots,
                keyframes_count=len(keyframes),
                skipped_idle=True,
                idle_reason="No meaningful content in generated summary",
            )

        # Step 4: Web enrichment for sports matches and contextual info (if not skipped)
        logger.debug("Enriching summary with web data...")
        enrichment_result = self.enricher.enrich_summary(summary, hour_start)
        if enrichment_result.enriched_count > 0:
            logger.info(f"Enriched {enrichment_result.enriched_count} items with web data")

        # Step 5: Generate note ID and paths
        note_id = str(uuid.uuid4())
        file_path = get_note_path(hour_start)
        ensure_note_directory(hour_start)

        # Step 6: Render and save Markdown
        logger.debug("Rendering Markdown note...")
        saved = self.renderer.render_to_file(
            summary=summary,
            note_id=note_id,
            hour_start=hour_start,
            hour_end=hour_end,
            file_path=file_path,
            location=evidence.locations[0] if evidence.locations else None,
            app_durations=evidence.app_durations if evidence.app_durations else None,
            calendar_events=evidence.calendar_events if evidence.calendar_events else None,
        )

        if not saved:
            return SummarizationResult(
                success=False,
                note_id=note_id,
                file_path=file_path,
                error="Failed to save Markdown file",
            )

        # Step 7: Store note in database
        logger.debug("Storing note in database...")
        self._store_note(
            note_id=note_id,
            hour_start=hour_start,
            hour_end=hour_end,
            file_path=file_path,
            summary=summary,
        )

        # Step 8: Extract and store entities
        logger.debug("Extracting entities...")
        links = self.entity_extractor.extract_and_store(summary, note_id)
        entities_count = len(links)

        # Step 9: Compute embedding
        logger.debug("Computing embedding...")
        embedding_result = self.embedding_computer.compute_for_note(
            note_id=note_id,
            summary=summary,
            hour_start=hour_start,
        )

        # Step 10: Clean up screenshot folder for this hour
        logger.debug("Cleaning up screenshot folder...")
        cleanup_success = delete_hourly_screenshot_dir(hour_start)
        if cleanup_success:
            logger.info(f"Deleted screenshot folder for {hour_start.isoformat()}")
        else:
            logger.warning(f"Failed to delete screenshot folder for {hour_start.isoformat()}")

        logger.info(f"Summarization complete for {hour_start.isoformat()}: {note_id}")

        return SummarizationResult(
            success=True,
            note_id=note_id,
            file_path=file_path,
            events_count=evidence.total_events,
            screenshots_count=evidence.total_screenshots,
            keyframes_count=len(keyframes),
            entities_count=entities_count,
            embedding_computed=embedding_result.success,
        )

    def _check_existing_note(self, hour_start: datetime) -> str | None:
        """Check if a note already exists for this hour."""
        conn = get_connection(self.db_path)
        try:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT note_id FROM notes
                WHERE note_type = 'hour'
                AND start_ts = ?
                """,
                (hour_start.isoformat(),),
            )
            row = cursor.fetchone()
            return row["note_id"] if row else None
        finally:
            conn.close()

    def _select_keyframes(
        self,
        hour_start: datetime,
        hour_end: datetime,
        evidence: HourlyEvidence,
    ) -> list[SelectedKeyframe]:
        """Select keyframes for the hour."""
        # Get screenshots from database
        conn = get_connection(self.db_path)
        try:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT s.screenshot_id, s.ts, s.monitor_id, s.path, s.fingerprint, s.diff_score,
                       e.app_id, e.app_name, e.window_title
                FROM screenshots s
                LEFT JOIN events e ON s.ts >= e.start_ts AND s.ts < e.end_ts
                WHERE s.ts >= ? AND s.ts < ?
                ORDER BY s.ts
                """,
                (hour_start.isoformat(), hour_end.isoformat()),
            )

            candidates = []
            for row in cursor.fetchall():
                try:
                    timestamp = datetime.fromisoformat(row["ts"])
                except (ValueError, TypeError):
                    continue

                # Ensure diff_score is a float
                diff_score_val = row["diff_score"]
                if diff_score_val is None:
                    diff_score_val = 0.0
                elif not isinstance(diff_score_val, (int, float)):
                    try:
                        diff_score_val = float(diff_score_val)
                    except (ValueError, TypeError):
                        diff_score_val = 0.0

                candidate = ScreenshotCandidate(
                    screenshot_id=row["screenshot_id"],
                    screenshot_path=Path(row["path"]),
                    timestamp=timestamp,
                    monitor_id=row["monitor_id"],
                    diff_score=float(diff_score_val),
                    fingerprint=row["fingerprint"] or "",
                    app_id=row["app_id"],
                    app_name=row["app_name"],
                    window_title=row["window_title"],
                )

                # Triage if using heuristic
                if self.use_heuristic_triage and isinstance(self.triager, HeuristicTriager):
                    triage_result = self.triager.triage(
                        screenshot_id=candidate.screenshot_id,
                        screenshot_path=candidate.screenshot_path,
                        timestamp=timestamp,
                        app_id=row["app_id"],
                        window_title=row["window_title"],
                        diff_score=float(diff_score_val) if diff_score_val else 0.5,
                    )
                    candidate.triage_result = triage_result

                candidates.append(candidate)

        finally:
            conn.close()

        # Select keyframes
        keyframes = self.keyframe_selector.select(candidates)

        # Limit for LLM call
        return keyframes[:MAX_KEYFRAMES_FOR_LLM]

    def _call_llm(
        self,
        evidence: HourlyEvidence,
        keyframes: list[SelectedKeyframe],
        image_detail: str = "auto",
    ) -> HourlySummarySchema | None:
        """
        Call the LLM for summarization.

        Args:
            evidence: Aggregated evidence for the hour
            keyframes: Selected keyframes with screenshots
            image_detail: Image detail level - "auto", "low", or "high"

        Returns:
            HourlySummarySchema or None if failed
        """
        try:
            # Build messages with specified detail level
            messages = build_vision_messages(
                evidence, keyframes, self.aggregator, image_detail=image_detail
            )

            client = self._get_client()
            response = client.chat.completions.create(
                model=self.model,
                messages=messages,
                max_completion_tokens=4096,
                response_format={"type": "json_object"},
            )

            response_text = response.choices[0].message.content or "{}"

            # Validate response
            result = validate_with_retry(response_text)

            if not result.valid:
                logger.error(f"LLM response validation failed: {result.error}")
                return None

            return result.data

        except Exception as e:
            logger.error(f"LLM call failed: {e}")
            return None

    def _call_llm_with_retry(
        self,
        evidence: HourlyEvidence,
        keyframes: list[SelectedKeyframe],
    ) -> HourlySummarySchema | None:
        """
        Call LLM with automatic retry using higher image detail if first attempt
        returns empty/placeholder content.

        This handles cases where the LLM needs more image detail to properly
        analyze the screenshots and extract meaningful activity information.

        Returns:
            HourlySummarySchema or None if all attempts failed
        """
        # First attempt with "auto" detail
        logger.debug("LLM call attempt 1 with image_detail='auto'")
        summary = self._call_llm(evidence, keyframes, image_detail="auto")

        if summary is None:
            return None

        # Check if we got meaningful content
        if self._has_meaningful_content(summary):
            return summary

        # Check if the summary is a known placeholder that indicates the LLM
        # couldn't properly analyze the images
        summary_lower = (summary.summary or "").lower()
        needs_retry = (
            "no summary available" in summary_lower
            or "no activity detected" in summary_lower
            or "insufficient evidence" in summary_lower
            or len(summary.activities) == 0
        )

        if needs_retry and evidence.total_screenshots > 0:
            logger.warning(
                f"LLM returned empty content with {evidence.total_screenshots} screenshots. "
                "Retrying with image_detail='high' for better analysis..."
            )

            # Retry with high detail - this gives the LLM full resolution images
            # to better read text and understand the screen content
            summary_retry = self._call_llm(evidence, keyframes, image_detail="high")

            if summary_retry is not None and self._has_meaningful_content(summary_retry):
                logger.info("Retry with high detail succeeded!")
                return summary_retry

            logger.warning("Retry with high detail also returned empty content")

        # Return the original summary (even if empty) for proper handling upstream
        return summary

    def _has_meaningful_content(self, summary: HourlySummarySchema) -> bool:
        """
        Check if the summary has meaningful content worth saving.

        This is a CRITICAL failsafe check that catches empty/placeholder notes
        that slipped through LLM verification. Uses strict heuristics to ensure
        we never save useless notes.

        IMPORTANT: This runs even when force=True to prevent saving garbage.

        Returns:
            True if note has meaningful content, False if it should be skipped
        """
        # Expanded list of empty indicators - these phrases indicate placeholder content
        empty_indicators = [
            "no summary available",
            "no activity detected",
            "no meaningful activity",
            "no activity details",
            "no details were captured",
            "no details captured",
            "insufficient evidence",
            "no evidence available",
            "no evidence to",
            "unable to generate",
            "could not generate",
            "nothing to summarize",
            "no notable activity",
            "missing note",
            "wasn't enough evidence",
            "isn't enough evidence",
            "not enough information",
            "not enough data",
            "no data available",
            "placeholder",
            "n/a",
            "none available",
            "activity unknown",
            "unknown activity",
            "no specific activity",
            "general computer use",  # Too vague
            "various tasks",  # Too vague
            "miscellaneous",  # Too vague
        ]

        # Check summary text for empty indicators
        if summary.summary:
            summary_lower = summary.summary.lower().strip()
            for indicator in empty_indicators:
                if indicator in summary_lower:
                    logger.info(f"Summary contains empty indicator: '{indicator}'")
                    return False
        else:
            logger.info("Summary text is empty")
            return False

        # Check if summary is too short (less than 50 chars is suspicious)
        # Real activity summaries should have meaningful descriptions
        if len(summary.summary.strip()) < 50:
            logger.info(f"Summary too short: {len(summary.summary.strip())} chars")
            return False

        # Check if there are any activities
        if not summary.activities:
            logger.info("No activities in summary")
            return False

        # Check if all activities are trivial (only contain generic descriptions)
        trivial_activities = [
            "idle",
            "lock screen",
            "screen saver",
            "screensaver",
            "sleep",
            "no activity",
            "system idle",
            "away",
            "afk",
            "inactive",
            "standby",
            "login screen",
            "desktop",  # Just showing desktop
            "finder",  # Just Finder with no specific task
            "blank screen",
            "waiting",
        ]
        real_activities = 0
        for activity in summary.activities:
            desc_lower = activity.description.lower() if activity.description else ""

            # Check if description is trivial
            is_trivial = any(t in desc_lower for t in trivial_activities)

            # Also check if it's just a generic app mention with no real description
            is_vague = len(desc_lower) < 15 or desc_lower in trivial_activities

            if not is_trivial and not is_vague:
                real_activities += 1

        if real_activities == 0:
            logger.info(f"All {len(summary.activities)} activities are trivial or too short/vague")
            return False

        # Check categories - empty categories usually mean empty note
        if not summary.categories:
            logger.info("No categories in summary")
            return False

        # Additional check: at least one activity must have a meaningful app
        has_real_app = False
        for activity in summary.activities:
            if activity.app and activity.app.lower() not in ["unknown", "n/a", "", "none"]:
                has_real_app = True
                break

        if not has_real_app:
            logger.info("No activities have a real app name")
            return False

        logger.debug(
            f"Content validation passed: {len(summary.activities)} activities, "
            f"{real_activities} non-trivial, {len(summary.categories)} categories"
        )
        return True

    def _verify_note_quality(
        self,
        summary: HourlySummarySchema,
        evidence: HourlyEvidence,
    ) -> dict:
        """
        Use LLM to verify if the generated note has meaningful content worth keeping.

        This is an additional verification step to prevent empty or low-quality notes
        from being saved. The LLM evaluates the summary and decides if it represents
        meaningful user activity.

        Args:
            summary: The generated summary to verify
            evidence: The evidence that was used to generate the summary

        Returns:
            dict with 'should_keep' (bool) and 'reason' (str)
        """
        # First, check if summary is clearly empty
        if not summary.summary or not summary.summary.strip():
            return {"should_keep": False, "reason": "Empty summary text"}

        # Check if there are any activities
        if not summary.activities:
            return {"should_keep": False, "reason": "No activities recorded"}

        # Build verification prompt
        verification_prompt = f"""You are evaluating whether a generated activity note should be kept or discarded.

The note should be KEPT if it contains:
- Meaningful user activity (work, learning, communication, etc.)
- Specific details about what the user was doing
- Information that would be useful to recall later

The note should be DISCARDED if:
- It only contains generic/placeholder text with no specific content
- It describes idle time, sleep mode, or screen savers
- It says there was no meaningful activity or insufficient evidence
- The activities are trivial (just showing lock screen, idle desktop, etc.)

Here is the generated summary:
"{summary.summary}"

Activities recorded:
{chr(10).join(f"- {a.description} ({a.app})" for a in summary.activities[:5])}

Number of screenshots analyzed: {evidence.total_screenshots}
Number of events tracked: {evidence.total_events}

Respond with ONLY a JSON object:
{{"should_keep": true/false, "reason": "brief explanation"}}"""

        try:
            client = self._get_client()
            response = client.chat.completions.create(
                model="gpt-4o-mini",  # Use fast model for verification
                messages=[{"role": "user", "content": verification_prompt}],
                max_tokens=100,
                response_format={"type": "json_object"},
            )

            result_text = response.choices[0].message.content or "{}"
            result = json.loads(result_text)

            should_keep = result.get("should_keep", True)
            reason = result.get("reason", "LLM verification")

            logger.debug(f"Note quality verification: keep={should_keep}, reason={reason}")

            return {"should_keep": should_keep, "reason": reason}

        except Exception as e:
            logger.warning(f"Note quality verification failed, defaulting to keep: {e}")
            # Default to keeping the note if verification fails
            return {"should_keep": True, "reason": "Verification failed, keeping by default"}

    def _generate_empty_note(
        self,
        hour_start: datetime,
        hour_end: datetime,
    ) -> SummarizationResult:
        """Generate an empty note for hours with no activity."""
        note_id = str(uuid.uuid4())
        file_path = get_note_path(hour_start)
        ensure_note_directory(hour_start)

        summary = generate_empty_summary(hour_start, hour_end, "No activity detected")

        # Render and save
        saved = self.renderer.render_to_file(
            summary=summary,
            note_id=note_id,
            hour_start=hour_start,
            hour_end=hour_end,
            file_path=file_path,
        )

        if not saved:
            return SummarizationResult(
                success=False,
                note_id=note_id,
                file_path=file_path,
                error="Failed to save empty note",
            )

        # Store in database
        self._store_note(
            note_id=note_id,
            hour_start=hour_start,
            hour_end=hour_end,
            file_path=file_path,
            summary=summary,
        )

        return SummarizationResult(
            success=True,
            note_id=note_id,
            file_path=file_path,
            events_count=0,
            screenshots_count=0,
        )

    def _store_note(
        self,
        note_id: str,
        hour_start: datetime,
        hour_end: datetime,
        file_path: Path,
        summary: HourlySummarySchema,
    ) -> None:
        """Store note metadata in the database."""
        conn = get_connection(self.db_path)
        try:
            cursor = conn.cursor()

            # Serialize summary to JSON
            json_payload = json.dumps(summary.model_dump())

            cursor.execute(
                """
                INSERT OR REPLACE INTO notes
                (note_id, note_type, start_ts, end_ts, file_path, json_payload, created_ts, updated_ts)
                VALUES (?, 'hour', ?, ?, ?, ?, ?, ?)
                """,
                (
                    note_id,
                    hour_start.isoformat(),
                    hour_end.isoformat(),
                    str(file_path),
                    json_payload,
                    datetime.now().isoformat(),
                    datetime.now().isoformat(),
                ),
            )
            conn.commit()
        finally:
            conn.close()


if __name__ == "__main__":
    import fire

    def summarize(
        hour: str | None = None,
        force: bool = False,
        db_path: str | None = None,
    ):
        """
        Summarize an hour.

        Args:
            hour: Hour in ISO format (e.g., '2025-01-15T14:00:00'), defaults to previous hour
            force: Force regeneration even if note exists
            db_path: Path to database
        """
        if hour:
            hour_start = datetime.fromisoformat(hour)
        else:
            now = datetime.now()
            hour_start = (now - timedelta(hours=1)).replace(minute=0, second=0, microsecond=0)

        summarizer = HourlySummarizer(db_path=db_path)
        result = summarizer.summarize_hour(hour_start, force=force)

        return {
            "success": result.success,
            "note_id": result.note_id,
            "file_path": str(result.file_path) if result.file_path else None,
            "error": result.error,
            "events_count": result.events_count,
            "screenshots_count": result.screenshots_count,
            "keyframes_count": result.keyframes_count,
            "entities_count": result.entities_count,
            "embedding_computed": result.embedding_computed,
        }

    def batch(
        start_hour: str,
        end_hour: str,
        force: bool = False,
        db_path: str | None = None,
    ):
        """
        Summarize multiple hours.

        Args:
            start_hour: Start hour in ISO format
            end_hour: End hour in ISO format
            force: Force regeneration
            db_path: Path to database
        """
        start = datetime.fromisoformat(start_hour).replace(minute=0, second=0, microsecond=0)
        end = datetime.fromisoformat(end_hour).replace(minute=0, second=0, microsecond=0)

        summarizer = HourlySummarizer(db_path=db_path)
        results = []

        current = start
        while current < end:
            result = summarizer.summarize_hour(current, force=force)
            results.append(
                {
                    "hour": current.isoformat(),
                    "success": result.success,
                    "note_id": result.note_id,
                }
            )
            current += timedelta(hours=1)

        return {
            "total": len(results),
            "successful": sum(1 for r in results if r["success"]),
            "results": results,
        }

    fire.Fire({"summarize": summarize, "batch": batch})
