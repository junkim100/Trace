"""
Daily Revision Prompt for Trace

Structured prompt for gpt-5.2 to revise hourly notes with full day context,
normalize entities, and suggest graph edges.

P6-01: Daily revision prompt
"""

from datetime import date

from src.core.config import get_user_profile

# Schema version for daily output validation
DAILY_SCHEMA_VERSION = 1

# Model for daily revision (more capable for analysis)
DAILY_MODEL = "gpt-5.2-2025-12-11"

DAILY_SCHEMA_DESCRIPTION = """
{
  "schema_version": 1,
  "day_summary": "3-5 sentence overview of the entire day's activities and themes",
  "primary_focus": "The main theme or activity type for the day",
  "accomplishments": ["List of key accomplishments or completed tasks"],
  "hourly_revisions": [
    {
      "hour": "HH:00",
      "note_id": "original note ID",
      "revised_summary": "Improved summary with day context",
      "revised_entities": [
        {
          "original_name": "Entity as originally captured",
          "canonical_name": "Normalized canonical name",
          "type": "entity type",
          "confidence": 0.0-1.0
        }
      ],
      "additional_context": "Any new insights with full day context"
    }
  ],
  "entity_normalizations": [
    {
      "original_names": ["variant1", "variant2"],
      "canonical_name": "The canonical/normalized name",
      "entity_type": "topic|app|domain|document|artist|track|video|game|person|project",
      "confidence": 0.0-1.0
    }
  ],
  "graph_edges": [
    {
      "from_entity": "entity name",
      "from_type": "entity type",
      "to_entity": "entity name",
      "to_type": "entity type",
      "edge_type": "ABOUT_TOPIC|WATCHED|LISTENED_TO|USED_APP|VISITED_DOMAIN|DOC_REFERENCE|CO_OCCURRED_WITH|STUDIED_WHILE",
      "weight": 0.0-1.0,
      "evidence": "Brief explanation of the relationship"
    }
  ],
  "top_entities": {
    "topics": [{"name": "...", "total_minutes": 123}],
    "apps": [{"name": "...", "total_minutes": 123}],
    "domains": [{"name": "...", "total_minutes": 123}],
    "media": [{"name": "...", "type": "track|video", "total_minutes": 123}]
  },
  "patterns": ["Observed patterns in the day's activities"],
  "location_summary": "Summary of locations visited during the day"
}
"""

DAILY_SYSTEM_PROMPT = f"""You are a daily revision agent for Trace, a personal second-brain application.

Your task is to analyze all hourly notes from a single day and perform several operations:

1. **Revise Hourly Notes**: With full day context, improve the summaries and add insights that weren't visible from single-hour perspective.

2. **Normalize Entities**: Identify entities that refer to the same thing but have different names. Choose the best canonical name.

3. **Build Graph Edges**: Identify meaningful relationships between entities that should be recorded in the knowledge graph.

4. **Generate Day Summary**: Create a comprehensive overview of the day.

## CRITICAL: Detecting Misattributed Activity

**Watch for these common false positives in hourly notes:**

### Desktop Wallpaper Confusion
- If an hourly note mentions "admiring", "viewing", or "looking at" a city skyline, landscape, or artistic image
- If it mentions System Settings → Wallpaper/Desktop without other meaningful context
- If it describes beautiful scenery that seems out of context with the user's typical work
- **These are likely descriptions of the DESKTOP WALLPAPER, not actual user activity**
- In your revision, REMOVE or MINIMIZE such misattributed content

### System Elements vs Actual Work
- Brief glimpses of Dock, Menubar, or Desktop are NOT activities
- Lock screen, screensaver appearances are idle time, not activity
- Notification banners are not meaningful activities unless acted upon

### Idle Misclassification
- If notes describe only the wallpaper/desktop without application activity
- If notes describe "appreciating" or "contemplating" static imagery
- **These should be marked as idle time or removed from the day summary**

When you see suspicious activity mentions (wallpaper, desktop backgrounds, scenery viewing without context):
1. Check if it fits with the user's actual work patterns
2. Consider if the user would realistically spend time "admiring" their wallpaper
3. Revise the summary to remove or correct the misattribution
4. Do NOT create entities or graph edges for wallpaper-related false positives

## Output Requirements

You MUST respond with valid JSON conforming to this schema:
{DAILY_SCHEMA_DESCRIPTION}

## Guidelines

### Hourly Revisions
- Improve summaries with context from other hours
- Don't change factual information, only add context
- Note when activities in one hour relate to activities in other hours
- Identify when multi-hour projects or sessions span multiple notes

### Entity Normalization
- Group variants that refer to the same entity (e.g., "VSCode", "VS Code", "Visual Studio Code")
- Choose the most commonly used or most official name as canonical
- Maintain type consistency (don't change entity types)
- Include all variants in original_names array

### Graph Edges
- Create edges only for meaningful relationships
- Prefer higher confidence for explicitly stated relationships
- Edge types:
  - ABOUT_TOPIC: Entity relates to a topic/concept
  - WATCHED: User watched this video/media
  - LISTENED_TO: User listened to this track/podcast
  - USED_APP: Topic/project used this application
  - VISITED_DOMAIN: Topic/project visited this domain
  - DOC_REFERENCE: Document references another entity
  - CO_OCCURRED_WITH: Entities appeared together
  - STUDIED_WHILE: Learning activity paired with another activity

### Top Entities
- Aggregate time spent with each entity across all hours
- Only include entities with significant time (> 5 minutes)
- Rank by total engagement time

### Patterns
- Note recurring themes or behaviors
- Identify productive patterns (e.g., "deep work periods in morning")
- Note any concerning patterns (e.g., "context switching frequently")

## Constraints

- Do NOT invent activities that weren't in the hourly notes
- Keep confidence scores realistic (0.8+ only for explicit mentions)
- Entity names should be lowercase except for proper nouns
- Weight edges 0-1 based on strength of relationship
- Location summary should aggregate all distinct locations
- REMOVE or MINIMIZE any wallpaper/background misattributions from the day summary
- Do NOT create entities for desktop wallpaper images (cityscapes, landscapes, etc.)
- Be skeptical of "idle time activities" that describe viewing static imagery

## Schema Version

The current schema version is {DAILY_SCHEMA_VERSION}. Include this in your response.
"""


def get_user_profile_context() -> str:
    """
    Get user profile context to include in prompts.

    Returns:
        String with user profile info, or empty string if no profile set.
    """
    profile = get_user_profile()

    # Check if any profile fields are set
    has_profile = any(
        profile.get(key) for key in ["name", "age", "interests", "languages", "additional_info"]
    )

    if not has_profile:
        return ""

    lines = ["## User Profile", ""]

    if profile.get("name"):
        lines.append(f"- Name: {profile['name']}")
    if profile.get("age"):
        lines.append(f"- Age: {profile['age']}")
    if profile.get("interests"):
        lines.append(f"- Interests & Hobbies: {profile['interests']}")
    if profile.get("languages"):
        lines.append(f"- Languages: {profile['languages']}")
    if profile.get("additional_info"):
        lines.append(f"- Additional Context: {profile['additional_info']}")

    lines.append("")
    lines.append(
        "Use this profile information to personalize the day summary and pattern recognition, understanding activities in context of the user's interests and background."
    )
    lines.append("")

    return "\n".join(lines)


def build_daily_system_prompt() -> str:
    """
    Build the daily system prompt with user profile context if available.

    Returns:
        Complete system prompt string.
    """
    profile_context = get_user_profile_context()

    if profile_context:
        return DAILY_SYSTEM_PROMPT + "\n" + profile_context
    return DAILY_SYSTEM_PROMPT


def build_daily_user_prompt(
    day: date,
    hourly_notes: list[dict],
) -> str:
    """
    Build the user prompt for daily revision.

    Args:
        day: The date being revised
        hourly_notes: List of hourly note data with structure:
            - note_id: str
            - hour: int (0-23)
            - summary: HourlySummarySchema dict
            - file_path: str

    Returns:
        Formatted user prompt string
    """
    lines = []

    # Header
    day_str = day.strftime("%A, %B %d, %Y")
    lines.append(f"# Daily Revision: {day_str}")
    lines.append("")

    # Statistics
    lines.append("## Day Overview")
    lines.append(f"- Total hours with activity: {len(hourly_notes)}")

    # Collect all unique entities across the day
    all_entities = set()
    all_topics = set()
    all_apps = set()
    all_domains = set()
    all_media = []

    for note in hourly_notes:
        summary = note.get("summary", {})
        for entity in summary.get("entities", []):
            all_entities.add((entity.get("name", ""), entity.get("type", "")))
        for topic in summary.get("topics", []):
            all_topics.add(topic.get("name", ""))
        for activity in summary.get("activities", []):
            if activity.get("app"):
                all_apps.add(activity.get("app"))
        for site in summary.get("websites", []):
            all_domains.add(site.get("domain", ""))
        media = summary.get("media", {})
        for item in media.get("listening", []):
            all_media.append(f"{item.get('artist', '')} - {item.get('track', '')}")
        for item in media.get("watching", []):
            all_media.append(item.get("title", ""))

    lines.append(f"- Total unique entities: {len(all_entities)}")
    lines.append(f"- Total unique topics: {len(all_topics)}")
    lines.append(f"- Total unique apps: {len(all_apps)}")
    lines.append(f"- Total unique domains: {len(all_domains)}")
    lines.append(f"- Total media items: {len(all_media)}")
    lines.append("")

    # Hourly notes
    lines.append("## Hourly Notes")
    lines.append("")

    for note in sorted(hourly_notes, key=lambda x: x.get("hour", 0)):
        hour = note.get("hour", 0)
        note_id = note.get("note_id", "unknown")
        summary = note.get("summary", {})

        lines.append(f"### Hour {hour:02d}:00 - {(hour + 1) % 24:02d}:00")
        lines.append(f"Note ID: `{note_id}`")
        lines.append("")

        # Summary
        lines.append(f"**Summary**: {summary.get('summary', 'No summary')}")
        lines.append("")

        # Categories
        categories = summary.get("categories", [])
        if categories:
            lines.append(f"**Categories**: {', '.join(categories)}")

        # Activities
        activities = summary.get("activities", [])
        if activities:
            lines.append("**Activities**:")
            for act in activities:
                time_range = f"{act.get('time_start', '??')}-{act.get('time_end', '??')}"
                app = f" ({act.get('app')})" if act.get("app") else ""
                lines.append(f"- [{time_range}]{app} {act.get('description', '')}")

        # Topics
        topics = summary.get("topics", [])
        if topics:
            topic_strs = [f"{t.get('name', '')} ({t.get('confidence', 0):.0%})" for t in topics]
            lines.append(f"**Topics**: {', '.join(topic_strs)}")

        # Entities
        entities = summary.get("entities", [])
        if entities:
            entity_strs = [f"{e.get('name', '')} [{e.get('type', '')}]" for e in entities]
            lines.append(f"**Entities**: {', '.join(entity_strs)}")

        # Media
        media = summary.get("media", {})
        listening = media.get("listening", [])
        watching = media.get("watching", [])
        if listening:
            for item in listening:
                duration = (item.get("duration_seconds") or 0) // 60
                lines.append(
                    f"**Listening**: {item.get('artist', '')} - {item.get('track', '')} ({duration}m)"
                )
        if watching:
            for item in watching:
                duration = (item.get("duration_seconds") or 0) // 60
                lines.append(f"**Watching**: {item.get('title', '')} ({duration}m)")

        # Documents
        documents = summary.get("documents", [])
        if documents:
            doc_strs = [f"{d.get('name', '')} [{d.get('type', '')}]" for d in documents]
            lines.append(f"**Documents**: {', '.join(doc_strs)}")

        # Websites
        websites = summary.get("websites", [])
        if websites:
            site_strs = [s.get("domain", "") for s in websites]
            lines.append(f"**Websites**: {', '.join(site_strs)}")

        # Co-activities
        co_activities = summary.get("co_activities", [])
        if co_activities:
            for co in co_activities:
                lines.append(
                    f"**Co-activity**: {co.get('primary', '')} while {co.get('secondary', '')}"
                )

        # Location
        location = summary.get("location")
        if location:
            lines.append(f"**Location**: {location}")

        lines.append("")
        lines.append("---")
        lines.append("")

    # Instructions
    lines.append("## Task")
    lines.append("")
    lines.append("Based on the hourly notes above:")
    lines.append("1. Generate a comprehensive day summary")
    lines.append("2. Revise each hourly note with full day context")
    lines.append("3. Normalize entities that refer to the same thing")
    lines.append("4. Identify graph edges between entities")
    lines.append("5. Calculate top entities by time spent")
    lines.append("6. Identify patterns in the day's activities")
    lines.append("")
    lines.append("Respond with valid JSON following the schema in the system prompt.")

    return "\n".join(lines)


def build_daily_messages(
    day: date,
    hourly_notes: list[dict],
) -> list[dict]:
    """
    Build messages for the daily revision LLM call.

    Args:
        day: The date being revised
        hourly_notes: List of hourly note data

    Returns:
        List of message dicts for the OpenAI API
    """
    messages = [{"role": "system", "content": build_daily_system_prompt()}]

    user_prompt = build_daily_user_prompt(day, hourly_notes)
    messages.append({"role": "user", "content": user_prompt})

    return messages


if __name__ == "__main__":
    import fire

    def show_schema():
        """Show the JSON schema for daily revision output."""
        print(DAILY_SCHEMA_DESCRIPTION)

    def show_system_prompt():
        """Show the system prompt."""
        print(DAILY_SYSTEM_PROMPT)

    def demo_user_prompt():
        """Show a demo user prompt with sample hourly notes."""
        sample_notes = [
            {
                "note_id": "note-001",
                "hour": 9,
                "summary": {
                    "summary": "Started the day reviewing emails and planning tasks.",
                    "categories": ["work", "communication"],
                    "activities": [
                        {
                            "time_start": "09:00",
                            "time_end": "09:30",
                            "description": "Checking emails",
                            "app": "Mail",
                            "category": "communication",
                        }
                    ],
                    "topics": [{"name": "project planning", "confidence": 0.8}],
                    "entities": [
                        {"name": "Mail", "type": "app", "confidence": 0.95},
                        {"name": "Project Alpha", "type": "project", "confidence": 0.7},
                    ],
                    "media": {"listening": [], "watching": []},
                    "documents": [],
                    "websites": [],
                    "co_activities": [],
                    "location": "Home Office",
                },
            },
            {
                "note_id": "note-002",
                "hour": 10,
                "summary": {
                    "summary": "Deep work session on Python project in VS Code.",
                    "categories": ["work", "coding"],
                    "activities": [
                        {
                            "time_start": "10:00",
                            "time_end": "11:00",
                            "description": "Writing Python code",
                            "app": "Visual Studio Code",
                            "category": "work",
                        }
                    ],
                    "topics": [
                        {"name": "Python", "confidence": 0.95},
                        {"name": "async programming", "confidence": 0.8},
                    ],
                    "entities": [
                        {"name": "VS Code", "type": "app", "confidence": 0.95},
                        {"name": "Python", "type": "topic", "confidence": 0.9},
                        {"name": "Project Alpha", "type": "project", "confidence": 0.85},
                    ],
                    "media": {
                        "listening": [
                            {
                                "artist": "Lofi Girl",
                                "track": "Study Beats",
                                "duration_seconds": 3600,
                            }
                        ],
                        "watching": [],
                    },
                    "documents": [],
                    "websites": [{"domain": "docs.python.org", "purpose": "Documentation"}],
                    "co_activities": [
                        {
                            "primary": "Coding",
                            "secondary": "Listening to music",
                            "relationship": "worked_while",
                        }
                    ],
                    "location": "Home Office",
                },
            },
        ]

        today = date.today()
        print(build_daily_user_prompt(today, sample_notes))

    fire.Fire(
        {
            "schema": show_schema,
            "system": show_system_prompt,
            "demo": demo_user_prompt,
        }
    )
