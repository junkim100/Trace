"""
Memory Extraction Guidelines

Explicit rules for determining what information is durable (stored in MEMORY.md)
vs transient (stays only in daily notes).

Inspired by clawdbot's memory system principles.
"""

# The core test for durability
DURABILITY_TEST = """
**Durability Test**: Ask "Will this likely be true in 30 days?"
- Yes → Extract to MEMORY.md (durable)
- No/Maybe → Keep in daily notes only (transient)
"""

# Categories of information that ARE durable
DURABLE_CATEGORIES = {
    "identity": "Name, role, company, location - stable personal facts",
    "preferences": "Consistent choices: dark mode, vim bindings, morning person",
    "patterns": "Recurring behaviors observed across multiple days",
    "skills": "Technologies, tools, expertise demonstrated repeatedly",
    "relationships": "Key people/organizations that appear multiple times",
    "goals": "Long-term aspirations mentioned more than once",
}

# Categories of information that are NOT durable
TRANSIENT_CATEGORIES = {
    "events": "One-time meetings, calls, deployments",
    "temporary_tasks": "Ad-hoc work with no continuation",
    "anomalies": "One-day deviations from normal patterns",
    "casual_mentions": "Topics mentioned once without follow-up",
}

# Full extraction rules for LLM prompts
EXTRACTION_RULES = """
## Memory Extraction Rules

### DURABLE (extract to MEMORY.md):
- Facts likely to remain true for weeks/months
- Patterns observed across 2+ days
- Explicitly stated preferences
- Technologies/tools used regularly (not one-off)
- Relationships that appear repeatedly
- Goals mentioned multiple times

### TRANSIENT (keep in daily notes only):
- Single-day events and meetings
- One-time tool usage or experiments
- Temporary project work without continuation
- Meeting notes without lasting insights
- Casual topic mentions with no follow-up
- Timestamps of specific actions

### SPECIFICITY GUIDELINES:
Be specific, not generic. Examples:
- "Uses VS Code with Vim bindings for Python" > "Uses an IDE"
- "Prefers TypeScript for frontend work" > "Likes TypeScript"
- "Deep focus sessions 9-11am daily" > "Morning person"
- "Works on Trace app (macOS digital memory)" > "Works on software"

### DEDUPLICATION:
Only extract NEW information not already in MEMORY.md.
Avoid restating existing facts in different words.
"""

# Memory header text for MEMORY.md
MEMORY_HEADER = """# User Memory

> This file contains learned information about the user based on their activity.
> Updated automatically by Trace. Manual edits are preserved.
>
> **Extraction Policy**: Only durable facts (likely true in 30+ days) are stored here.
> Daily events and transient information stay in daily notes.

Last updated: {timestamp}

---
"""


def get_extraction_prompt_guidelines() -> str:
    """
    Get the full extraction guidelines formatted for LLM prompts.

    Returns:
        String containing all extraction rules and durability test
    """
    return f"""
{EXTRACTION_RULES}

{DURABILITY_TEST}
""".strip()


def get_durable_categories_description() -> str:
    """
    Get a description of what counts as durable information.

    Returns:
        Formatted string describing durable categories
    """
    lines = ["**Durable Information Categories:**"]
    for category, description in DURABLE_CATEGORIES.items():
        lines.append(f"- **{category}**: {description}")
    return "\n".join(lines)


def get_transient_categories_description() -> str:
    """
    Get a description of what counts as transient information.

    Returns:
        Formatted string describing transient categories
    """
    lines = ["**Transient Information (do not extract):**"]
    for category, description in TRANSIENT_CATEGORIES.items():
        lines.append(f"- **{category}**: {description}")
    return "\n".join(lines)
