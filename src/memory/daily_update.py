"""
Daily Memory Update for Trace

Inspired by clawdbot's memory system, this module automatically updates
MEMORY.md based on daily notes. It runs after the daily job completes
to extract durable facts, patterns, and insights from the day's activity.

Key principles (from clawdbot):
- Extract DURABLE facts only (things likely to remain true)
- Be SPECIFIC, not generic
- Prioritize EXPLICIT over inferred information
- Track patterns over time
"""

import json
import logging
from datetime import datetime
from typing import Any

from openai import OpenAI

from src.core.config import get_api_key
from src.core.paths import DB_PATH, NOTES_DIR
from src.db.migrations import get_connection
from src.memory.guidelines import get_extraction_prompt_guidelines
from src.memory.memory import (
    MEMORY_EXTRACTION_MODEL,
    MemoryLogEntry,
    get_memory_manager,
)

logger = logging.getLogger(__name__)


def get_daily_note_content(day: datetime) -> str | None:
    """
    Get the content of the daily note for a specific day.

    Args:
        day: The day to get the note for

    Returns:
        The note content or None if not found
    """
    day_str = day.strftime("%Y%m%d")
    note_path = (
        NOTES_DIR
        / day.strftime("%Y")
        / day.strftime("%m")
        / day.strftime("%d")
        / f"day-{day_str}.md"
    )

    if note_path.exists():
        return note_path.read_text(encoding="utf-8")

    # Try to get from database
    conn = get_connection(DB_PATH)
    try:
        cursor = conn.cursor()
        day_start = day.replace(hour=0, minute=0, second=0, microsecond=0)
        day_end = day.replace(hour=23, minute=59, second=59, microsecond=999999)

        cursor.execute(
            """
            SELECT json_payload, file_path
            FROM notes
            WHERE note_type = 'day'
            AND start_ts >= ? AND start_ts <= ?
            ORDER BY start_ts DESC
            LIMIT 1
            """,
            (day_start.isoformat(), day_end.isoformat()),
        )
        row = cursor.fetchone()

        if row:
            # Try to read from file_path first
            if row["file_path"]:
                from pathlib import Path

                file_path = Path(row["file_path"])
                if file_path.exists():
                    return file_path.read_text(encoding="utf-8")
            # Fall back to json_payload
            if row["json_payload"]:
                payload = json.loads(row["json_payload"])
                return payload.get("summary", "")

    finally:
        conn.close()

    return None


def get_recent_hourly_summaries(day: datetime, limit: int = 24) -> list[dict]:
    """
    Get hourly note summaries for a day.

    Args:
        day: The day to get summaries for
        limit: Maximum number of summaries

    Returns:
        List of summary dictionaries
    """
    conn = get_connection(DB_PATH)
    try:
        cursor = conn.cursor()
        day_start = day.replace(hour=0, minute=0, second=0, microsecond=0)
        day_end = day.replace(hour=23, minute=59, second=59, microsecond=999999)

        cursor.execute(
            """
            SELECT start_ts, json_payload
            FROM notes
            WHERE note_type = 'hour'
            AND start_ts >= ? AND start_ts <= ?
            ORDER BY start_ts
            LIMIT ?
            """,
            (day_start.isoformat(), day_end.isoformat(), limit),
        )

        summaries = []
        for row in cursor.fetchall():
            if row["json_payload"]:
                try:
                    payload = json.loads(row["json_payload"])
                    summary = payload.get("summary", "")
                    if summary:
                        summaries.append(
                            {
                                "timestamp": row["start_ts"],
                                "summary": summary,
                                "entities": payload.get("entities", []),
                            }
                        )
                except json.JSONDecodeError:
                    pass

        return summaries

    finally:
        conn.close()


def extract_memory_updates(
    daily_note: str,
    hourly_summaries: list[dict],
    existing_memory_context: str,
    api_key: str | None = None,
) -> dict[str, Any]:
    """
    Use LLM to extract memory updates from daily activity.

    Inspired by clawdbot's approach:
    - Focus on DURABLE facts (things that remain true)
    - Extract specific, actionable information
    - Identify patterns and behavioral insights
    - Avoid one-time events unless significant

    Args:
        daily_note: Content of the daily note
        hourly_summaries: List of hourly summaries with timestamps
        existing_memory_context: Current memory context for deduplication
        api_key: OpenAI API key

    Returns:
        Dictionary with extracted updates
    """
    if not api_key:
        api_key = get_api_key()
    if not api_key:
        raise ValueError("No API key available")

    client = OpenAI(api_key=api_key)

    # Format hourly summaries
    formatted_hourly = []
    for s in hourly_summaries:
        ts = s["timestamp"][:16] if s["timestamp"] else "Unknown"
        formatted_hourly.append(f"[{ts}] {s['summary']}")

    hourly_context = (
        "\n".join(formatted_hourly) if formatted_hourly else "No hourly data available."
    )

    # Get guidelines from centralized module
    guidelines = get_extraction_prompt_guidelines()

    prompt = f"""You are analyzing a day's activity to extract DURABLE memory updates.

## Daily Summary
{daily_note}

## Hourly Activity Timeline
{hourly_context}

## Current Memory (avoid duplicating)
{existing_memory_context if existing_memory_context else "Memory is empty - extract foundational facts."}

---

{guidelines}

---

## Required Output

Return a JSON object with ONLY NEW information to add:

```json
{{
    "profile_updates": {{
        "name": "only if newly discovered",
        "current_role": "only if changed or newly discovered",
        "company": "only if mentioned and new"
    }},
    "technical_updates": {{
        "primary_stack": ["NEW technologies observed being used regularly"],
        "tools_platforms": ["NEW tools observed in regular use"]
    }},
    "current_focus_updates": {{
        "active_projects": ["NEW projects being worked on"],
        "learning_goals": ["NEW things being learned"]
    }},
    "work_pattern_updates": {{
        "daily_rhythms": ["NEW timing patterns observed"],
        "work_style": ["NEW work approach patterns"]
    }},
    "interest_updates": {{
        "professional": ["NEW professional interests"],
        "personal_hobbies": ["NEW personal interests or activities"]
    }},
    "relationship_updates": {{
        "key_people": ["NEW collaborators or contacts mentioned"],
        "organizations": ["NEW organizations mentioned"]
    }},
    "context_updates": {{
        "key_facts": ["NEW durable facts worth remembering"],
        "goals_aspirations": ["NEW goals mentioned or implied"]
    }},
    "insight_updates": {{
        "observed_patterns": ["NEW behavioral patterns"],
        "productivity_indicators": ["NEW productivity correlations"]
    }},
    "memory_log_entry": "Brief summary of what was learned today (1-2 sentences)"
}}
```

RULES:
- Return ONLY valid JSON
- Use empty strings "" and empty arrays [] for categories with nothing new
- Only include genuinely NEW information not in current memory
- Be concise but specific
- The memory_log_entry should summarize the day's key learning"""

    try:
        response = client.chat.completions.create(
            model=MEMORY_EXTRACTION_MODEL,
            messages=[
                {
                    "role": "system",
                    "content": """You are a memory extraction system that identifies durable,
actionable information from daily activity logs. You focus on patterns, preferences,
and facts that will remain relevant over time. You avoid duplicating existing knowledge
and only extract genuinely new information.""",
                },
                {"role": "user", "content": prompt},
            ],
            temperature=0.2,
            max_completion_tokens=2000,
        )

        result_text = response.choices[0].message.content or ""

        # Parse JSON
        if "```json" in result_text:
            result_text = result_text.split("```json")[1].split("```")[0]
        elif "```" in result_text:
            result_text = result_text.split("```")[1].split("```")[0]

        return json.loads(result_text.strip())

    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse memory extraction response: {e}")
        return {}
    except Exception as e:
        logger.error(f"Memory extraction failed: {e}")
        return {}


def apply_memory_updates(updates: dict[str, Any]) -> int:
    """
    Apply extracted updates to MEMORY.md.

    Args:
        updates: Dictionary of updates from extract_memory_updates

    Returns:
        Number of items added
    """
    manager = get_memory_manager()
    memory = manager.get_memory()
    items_added = 0

    def is_empty_or_placeholder(value: str | None) -> bool:
        """Check if a value is empty or a placeholder from the template."""
        if not value:
            return True
        # Check for template placeholders (start with "- **" or contain placeholder text)
        value_stripped = value.strip()
        if value_stripped.startswith("- **"):
            return True
        if "_will be" in value_stripped.lower():
            return True
        return False

    def add_to_list(target: list, items: list | None) -> int:
        """Add items to list, avoiding duplicates."""
        added = 0
        for item in items or []:
            if item and item not in target:
                target.append(item)
                added += 1
        return added

    # Profile updates
    profile = updates.get("profile_updates", {})
    if profile.get("name") and is_empty_or_placeholder(memory.profile.name):
        memory.profile.name = profile["name"]
        items_added += 1
    if profile.get("current_role") and is_empty_or_placeholder(memory.profile.current_role):
        memory.profile.current_role = profile["current_role"]
        items_added += 1
    if profile.get("company") and is_empty_or_placeholder(memory.profile.company):
        memory.profile.company = profile["company"]
        items_added += 1

    # Technical updates
    tech = updates.get("technical_updates", {})
    items_added += add_to_list(memory.technical.primary_stack, tech.get("primary_stack"))
    items_added += add_to_list(memory.technical.tools_platforms, tech.get("tools_platforms"))

    # Current focus updates
    focus = updates.get("current_focus_updates", {})
    items_added += add_to_list(memory.current_focus.active_projects, focus.get("active_projects"))
    items_added += add_to_list(memory.current_focus.learning_goals, focus.get("learning_goals"))

    # Work pattern updates
    patterns = updates.get("work_pattern_updates", {})
    items_added += add_to_list(memory.work_patterns.daily_rhythms, patterns.get("daily_rhythms"))
    items_added += add_to_list(memory.work_patterns.work_style, patterns.get("work_style"))

    # Interest updates
    interests = updates.get("interest_updates", {})
    items_added += add_to_list(memory.interests.professional, interests.get("professional"))
    items_added += add_to_list(memory.interests.personal_hobbies, interests.get("personal_hobbies"))

    # Relationship updates
    relationships = updates.get("relationship_updates", {})
    items_added += add_to_list(memory.relationships.key_people, relationships.get("key_people"))
    items_added += add_to_list(
        memory.relationships.organizations, relationships.get("organizations")
    )

    # Context updates
    context = updates.get("context_updates", {})
    items_added += add_to_list(memory.context.key_facts, context.get("key_facts"))
    items_added += add_to_list(memory.context.goals_aspirations, context.get("goals_aspirations"))

    # Insight updates
    insights = updates.get("insight_updates", {})
    items_added += add_to_list(memory.insights.observed_patterns, insights.get("observed_patterns"))
    items_added += add_to_list(
        memory.insights.productivity_indicators, insights.get("productivity_indicators")
    )

    # Add memory log entry
    log_entry = updates.get("memory_log_entry", "")
    if log_entry:
        memory.memory_log.append(
            MemoryLogEntry(
                timestamp=datetime.now(),
                content=log_entry,
                category="daily",
            )
        )
        # Keep only last 50 entries
        if len(memory.memory_log) > 50:
            memory.memory_log = memory.memory_log[-50:]

    # Save
    if items_added > 0 or log_entry:
        manager.save()

    return items_added


def update_memory_from_daily_note(day: datetime, api_key: str | None = None) -> dict[str, Any]:
    """
    Main function to update MEMORY.md from a day's notes.

    This should be called AFTER the daily note is generated.

    Args:
        day: The day to process
        api_key: OpenAI API key

    Returns:
        Result dictionary
    """
    day_str = day.strftime("%Y-%m-%d")
    logger.info(f"Updating memory from daily note for {day_str}")

    # Get daily note content
    daily_note = get_daily_note_content(day)
    if not daily_note:
        logger.info(f"No daily note found for {day_str}")
        return {
            "success": True,
            "day": day_str,
            "message": "No daily note found",
            "items_added": 0,
        }

    # Get hourly summaries for context
    hourly_summaries = get_recent_hourly_summaries(day)

    # Get existing memory context
    manager = get_memory_manager()
    memory = manager.get_memory()
    existing_context = memory.get_context_for_llm()

    # Extract updates
    updates = extract_memory_updates(
        daily_note=daily_note,
        hourly_summaries=hourly_summaries,
        existing_memory_context=existing_context,
        api_key=api_key,
    )

    if not updates:
        logger.info(f"No memory updates extracted for {day_str}")
        return {
            "success": True,
            "day": day_str,
            "message": "No new information to add",
            "items_added": 0,
        }

    # Apply updates
    items_added = apply_memory_updates(updates)

    logger.info(f"Memory update complete for {day_str}: {items_added} items added")

    return {
        "success": True,
        "day": day_str,
        "items_added": items_added,
        "updates": updates,
    }


if __name__ == "__main__":
    from datetime import timedelta

    import fire

    def update(day: str | None = None):
        """
        Update memory from a day's notes.

        Args:
            day: Date in YYYY-MM-DD format (defaults to yesterday)
        """
        if day:
            target_day = datetime.strptime(day, "%Y-%m-%d")
        else:
            target_day = datetime.now() - timedelta(days=1)

        return update_memory_from_daily_note(target_day)

    def show_daily(day: str | None = None):
        """Show the daily note content."""
        if day:
            target_day = datetime.strptime(day, "%Y-%m-%d")
        else:
            target_day = datetime.now() - timedelta(days=1)

        content = get_daily_note_content(target_day)
        if content:
            print(content)
        else:
            print(f"No daily note found for {target_day.strftime('%Y-%m-%d')}")

    fire.Fire(
        {
            "update": update,
            "show": show_daily,
        }
    )
