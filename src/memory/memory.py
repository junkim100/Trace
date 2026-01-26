"""
User Memory System for Trace

This module manages persistent user memory stored in MEMORY.md.
Memory includes:
- User profile (name, age, interests, languages)
- Learned preferences and patterns
- Important facts about the user
- Conversation insights

The memory is stored in markdown format for human readability
and easy parsing by LLMs.
"""

import logging
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from src.core.paths import DATA_ROOT

logger = logging.getLogger(__name__)

# Memory file path
MEMORY_PATH: Path = DATA_ROOT / "MEMORY.md"

# Default memory template
DEFAULT_MEMORY_TEMPLATE = """# User Memory

Last updated: {timestamp}

## Profile

- **Name**:
- **Age**:
- **Languages**:
- **Location**:
- **Occupation**:

## Interests & Hobbies

_No interests recorded yet. The app will learn about your interests over time._

## Preferences

_No preferences recorded yet. The app will learn your preferences through conversations._

## Important Facts

_No facts recorded yet. Important things about you will be stored here._

## Work & Projects

_No work information recorded yet._

## Learned Patterns

_Patterns about your behavior will be recorded here as the app learns from your activity._

## Conversation Insights

_Insights from conversations will be recorded here._
"""


@dataclass
class UserProfile:
    """User's basic profile information."""

    name: str = ""
    age: str = ""
    languages: str = ""
    location: str = ""
    occupation: str = ""

    def to_dict(self) -> dict[str, str]:
        return {
            "name": self.name,
            "age": self.age,
            "languages": self.languages,
            "location": self.location,
            "occupation": self.occupation,
        }

    @classmethod
    def from_dict(cls, data: dict[str, str]) -> "UserProfile":
        return cls(
            name=data.get("name", ""),
            age=data.get("age", ""),
            languages=data.get("languages", ""),
            location=data.get("location", ""),
            occupation=data.get("occupation", ""),
        )


@dataclass
class MemorySection:
    """A section of the memory file."""

    title: str
    content: list[str] = field(default_factory=list)

    def to_markdown(self) -> str:
        """Convert section to markdown."""
        lines = [f"## {self.title}", ""]
        lines.extend(self.content)
        return "\n".join(lines)

    def add_item(self, item: str):
        """Add an item to the section."""
        if item not in self.content:
            self.content.append(item)

    def remove_item(self, item: str):
        """Remove an item from the section."""
        if item in self.content:
            self.content.remove(item)


@dataclass
class UserMemory:
    """Complete user memory structure."""

    profile: UserProfile = field(default_factory=UserProfile)
    interests: list[str] = field(default_factory=list)
    preferences: list[str] = field(default_factory=list)
    important_facts: list[str] = field(default_factory=list)
    work_projects: list[str] = field(default_factory=list)
    learned_patterns: list[str] = field(default_factory=list)
    conversation_insights: list[str] = field(default_factory=list)
    last_updated: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "profile": self.profile.to_dict(),
            "interests": self.interests,
            "preferences": self.preferences,
            "important_facts": self.important_facts,
            "work_projects": self.work_projects,
            "learned_patterns": self.learned_patterns,
            "conversation_insights": self.conversation_insights,
            "last_updated": self.last_updated.isoformat(),
        }

    def to_markdown(self) -> str:
        """Convert to markdown format."""
        lines = [
            "# User Memory",
            "",
            f"Last updated: {self.last_updated.strftime('%Y-%m-%d %H:%M:%S')}",
            "",
            "## Profile",
            "",
            f"- **Name**: {self.profile.name}",
            f"- **Age**: {self.profile.age}",
            f"- **Languages**: {self.profile.languages}",
            f"- **Location**: {self.profile.location}",
            f"- **Occupation**: {self.profile.occupation}",
            "",
            "## Interests & Hobbies",
            "",
        ]

        if self.interests:
            for interest in self.interests:
                lines.append(f"- {interest}")
        else:
            lines.append(
                "_No interests recorded yet. The app will learn about your interests over time._"
            )

        lines.extend(["", "## Preferences", ""])
        if self.preferences:
            for pref in self.preferences:
                lines.append(f"- {pref}")
        else:
            lines.append(
                "_No preferences recorded yet. The app will learn your preferences through conversations._"
            )

        lines.extend(["", "## Important Facts", ""])
        if self.important_facts:
            for fact in self.important_facts:
                lines.append(f"- {fact}")
        else:
            lines.append("_No facts recorded yet. Important things about you will be stored here._")

        lines.extend(["", "## Work & Projects", ""])
        if self.work_projects:
            for project in self.work_projects:
                lines.append(f"- {project}")
        else:
            lines.append("_No work information recorded yet._")

        lines.extend(["", "## Learned Patterns", ""])
        if self.learned_patterns:
            for pattern in self.learned_patterns:
                lines.append(f"- {pattern}")
        else:
            lines.append(
                "_Patterns about your behavior will be recorded here as the app learns from your activity._"
            )

        lines.extend(["", "## Conversation Insights", ""])
        if self.conversation_insights:
            for insight in self.conversation_insights:
                lines.append(f"- {insight}")
        else:
            lines.append("_Insights from conversations will be recorded here._")

        lines.append("")  # Final newline
        return "\n".join(lines)

    def get_context_for_llm(self) -> str:
        """Get a formatted context string for LLM prompts."""
        parts = []

        if self.profile.name:
            parts.append(f"User's name: {self.profile.name}")
        if self.profile.age:
            parts.append(f"Age: {self.profile.age}")
        if self.profile.occupation:
            parts.append(f"Occupation: {self.profile.occupation}")
        if self.profile.languages:
            parts.append(f"Languages: {self.profile.languages}")
        if self.profile.location:
            parts.append(f"Location: {self.profile.location}")

        if self.interests:
            parts.append(f"Interests: {', '.join(self.interests[:5])}")

        if self.preferences:
            parts.append(f"Preferences: {'; '.join(self.preferences[:3])}")

        if self.important_facts:
            parts.append(f"Important facts: {'; '.join(self.important_facts[:3])}")

        if self.work_projects:
            parts.append(f"Current work/projects: {'; '.join(self.work_projects[:3])}")

        if not parts:
            return ""

        return "User context:\n" + "\n".join(f"- {p}" for p in parts)


class MemoryManager:
    """
    Manages user memory operations.

    Handles loading, saving, and updating the MEMORY.md file.
    """

    def __init__(self, memory_path: Path | None = None):
        """
        Initialize the memory manager.

        Args:
            memory_path: Optional custom path for memory file
        """
        self.memory_path = memory_path or MEMORY_PATH
        self._memory: UserMemory | None = None

    def load(self) -> UserMemory:
        """
        Load memory from file.

        Returns:
            UserMemory object
        """
        if not self.memory_path.exists():
            logger.info(f"Memory file not found, creating default: {self.memory_path}")
            self._memory = UserMemory()
            self.save()
            return self._memory

        try:
            content = self.memory_path.read_text(encoding="utf-8")
            self._memory = self._parse_markdown(content)
            logger.debug(f"Loaded memory from {self.memory_path}")
            return self._memory
        except Exception as e:
            logger.error(f"Failed to load memory: {e}")
            self._memory = UserMemory()
            return self._memory

    def save(self) -> bool:
        """
        Save memory to file.

        Returns:
            True if saved successfully
        """
        if self._memory is None:
            self._memory = UserMemory()

        try:
            self._memory.last_updated = datetime.now()
            self.memory_path.parent.mkdir(parents=True, exist_ok=True)
            self.memory_path.write_text(self._memory.to_markdown(), encoding="utf-8")
            logger.info(f"Saved memory to {self.memory_path}")
            return True
        except Exception as e:
            logger.error(f"Failed to save memory: {e}")
            return False

    def get_memory(self) -> UserMemory:
        """Get current memory, loading if necessary."""
        if self._memory is None:
            self.load()
        return self._memory  # type: ignore

    def update_profile(self, profile_data: dict[str, str]) -> bool:
        """
        Update user profile.

        Args:
            profile_data: Dictionary with profile fields

        Returns:
            True if saved successfully
        """
        memory = self.get_memory()

        if "name" in profile_data:
            memory.profile.name = profile_data["name"]
        if "age" in profile_data:
            memory.profile.age = profile_data["age"]
        if "languages" in profile_data:
            memory.profile.languages = profile_data["languages"]
        if "location" in profile_data:
            memory.profile.location = profile_data["location"]
        if "occupation" in profile_data:
            memory.profile.occupation = profile_data["occupation"]

        return self.save()

    def add_interest(self, interest: str) -> bool:
        """Add an interest."""
        memory = self.get_memory()
        if interest and interest not in memory.interests:
            memory.interests.append(interest)
            return self.save()
        return True

    def add_preference(self, preference: str) -> bool:
        """Add a preference."""
        memory = self.get_memory()
        if preference and preference not in memory.preferences:
            memory.preferences.append(preference)
            return self.save()
        return True

    def add_fact(self, fact: str) -> bool:
        """Add an important fact."""
        memory = self.get_memory()
        if fact and fact not in memory.important_facts:
            memory.important_facts.append(fact)
            return self.save()
        return True

    def add_work_project(self, project: str) -> bool:
        """Add a work/project item."""
        memory = self.get_memory()
        if project and project not in memory.work_projects:
            memory.work_projects.append(project)
            return self.save()
        return True

    def add_pattern(self, pattern: str) -> bool:
        """Add a learned pattern."""
        memory = self.get_memory()
        if pattern and pattern not in memory.learned_patterns:
            memory.learned_patterns.append(pattern)
            return self.save()
        return True

    def add_insight(self, insight: str) -> bool:
        """Add a conversation insight."""
        memory = self.get_memory()
        if insight and insight not in memory.conversation_insights:
            # Keep only last 20 insights
            if len(memory.conversation_insights) >= 20:
                memory.conversation_insights = memory.conversation_insights[-19:]
            memory.conversation_insights.append(insight)
            return self.save()
        return True

    def remove_item(self, section: str, item: str) -> bool:
        """
        Remove an item from a section.

        Args:
            section: Section name (interests, preferences, facts, work, patterns, insights)
            item: Item to remove

        Returns:
            True if saved successfully
        """
        memory = self.get_memory()

        section_map = {
            "interests": memory.interests,
            "preferences": memory.preferences,
            "facts": memory.important_facts,
            "important_facts": memory.important_facts,
            "work": memory.work_projects,
            "work_projects": memory.work_projects,
            "patterns": memory.learned_patterns,
            "learned_patterns": memory.learned_patterns,
            "insights": memory.conversation_insights,
            "conversation_insights": memory.conversation_insights,
        }

        section_list = section_map.get(section.lower())
        if section_list is not None and item in section_list:
            section_list.remove(item)
            return self.save()

        return False

    def bulk_update(self, updates: dict[str, Any]) -> bool:
        """
        Perform bulk updates to memory.

        Args:
            updates: Dictionary with section names as keys and lists/dicts as values

        Returns:
            True if saved successfully
        """
        memory = self.get_memory()

        if "profile" in updates and isinstance(updates["profile"], dict):
            self.update_profile(updates["profile"])

        if "interests" in updates and isinstance(updates["interests"], list):
            for interest in updates["interests"]:
                if interest and interest not in memory.interests:
                    memory.interests.append(interest)

        if "preferences" in updates and isinstance(updates["preferences"], list):
            for pref in updates["preferences"]:
                if pref and pref not in memory.preferences:
                    memory.preferences.append(pref)

        if "facts" in updates or "important_facts" in updates:
            facts = updates.get("facts") or updates.get("important_facts") or []
            if isinstance(facts, list):
                for fact in facts:
                    if fact and fact not in memory.important_facts:
                        memory.important_facts.append(fact)

        if "work" in updates or "work_projects" in updates:
            work = updates.get("work") or updates.get("work_projects") or []
            if isinstance(work, list):
                for item in work:
                    if item and item not in memory.work_projects:
                        memory.work_projects.append(item)

        if "patterns" in updates or "learned_patterns" in updates:
            patterns = updates.get("patterns") or updates.get("learned_patterns") or []
            if isinstance(patterns, list):
                for pattern in patterns:
                    if pattern and pattern not in memory.learned_patterns:
                        memory.learned_patterns.append(pattern)

        if "insights" in updates or "conversation_insights" in updates:
            insights = updates.get("insights") or updates.get("conversation_insights") or []
            if isinstance(insights, list):
                for insight in insights:
                    self.add_insight(insight)

        return self.save()

    def _parse_markdown(self, content: str) -> UserMemory:
        """
        Parse markdown content into UserMemory.

        Args:
            content: Markdown content

        Returns:
            UserMemory object
        """
        memory = UserMemory()

        # Parse last updated
        updated_match = re.search(r"Last updated:\s*(.+)", content)
        if updated_match:
            try:
                memory.last_updated = datetime.fromisoformat(updated_match.group(1).strip())
            except ValueError:
                try:
                    memory.last_updated = datetime.strptime(
                        updated_match.group(1).strip(), "%Y-%m-%d %H:%M:%S"
                    )
                except ValueError:
                    pass

        # Parse profile section
        profile_match = re.search(r"## Profile\s*\n(.*?)(?=\n## |\Z)", content, re.DOTALL)
        if profile_match:
            profile_content = profile_match.group(1)

            name_match = re.search(r"\*\*Name\*\*:\s*(.+)", profile_content)
            if name_match:
                memory.profile.name = name_match.group(1).strip()

            age_match = re.search(r"\*\*Age\*\*:\s*(.+)", profile_content)
            if age_match:
                memory.profile.age = age_match.group(1).strip()

            lang_match = re.search(r"\*\*Languages\*\*:\s*(.+)", profile_content)
            if lang_match:
                memory.profile.languages = lang_match.group(1).strip()

            loc_match = re.search(r"\*\*Location\*\*:\s*(.+)", profile_content)
            if loc_match:
                memory.profile.location = loc_match.group(1).strip()

            occ_match = re.search(r"\*\*Occupation\*\*:\s*(.+)", profile_content)
            if occ_match:
                memory.profile.occupation = occ_match.group(1).strip()

        # Parse list sections
        def parse_list_section(section_name: str) -> list[str]:
            pattern = rf"## {re.escape(section_name)}\s*\n(.*?)(?=\n## |\Z)"
            match = re.search(pattern, content, re.DOTALL)
            if not match:
                return []

            section_content = match.group(1)
            items = []
            for line in section_content.split("\n"):
                line = line.strip()
                if line.startswith("- ") and not line.startswith("_"):
                    items.append(line[2:].strip())
            return items

        memory.interests = parse_list_section("Interests & Hobbies")
        memory.preferences = parse_list_section("Preferences")
        memory.important_facts = parse_list_section("Important Facts")
        memory.work_projects = parse_list_section("Work & Projects")
        memory.learned_patterns = parse_list_section("Learned Patterns")
        memory.conversation_insights = parse_list_section("Conversation Insights")

        return memory


# Global instance
_memory_manager: MemoryManager | None = None


def get_memory_manager() -> MemoryManager:
    """Get the global memory manager instance."""
    global _memory_manager
    if _memory_manager is None:
        _memory_manager = MemoryManager()
    return _memory_manager


def get_user_memory() -> UserMemory:
    """Get the current user memory."""
    return get_memory_manager().get_memory()


def get_memory_context() -> str:
    """Get memory context formatted for LLM prompts."""
    return get_user_memory().get_context_for_llm()


def populate_memory_from_notes(api_key: str | None = None, max_notes: int = 50) -> dict:
    """
    Populate memory by analyzing existing notes.

    This function reads notes from the database and uses an LLM to extract
    user information such as interests, work projects, and patterns.

    Args:
        api_key: OpenAI API key (uses config if not provided)
        max_notes: Maximum number of notes to analyze

    Returns:
        Dictionary with population results
    """
    import json

    from openai import OpenAI

    from src.core.config import get_api_key
    from src.core.paths import DB_PATH
    from src.db.migrations import get_connection

    logger.info("Starting memory population from notes...")

    # Get API key
    if not api_key:
        api_key = get_api_key()
    if not api_key:
        return {"success": False, "error": "No API key available"}

    # Get notes from database
    conn = get_connection(DB_PATH)
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT note_id, note_type, json_payload
            FROM notes
            WHERE json_payload IS NOT NULL AND json_payload != ''
            ORDER BY start_ts DESC
            LIMIT ?
            """,
            (max_notes,),
        )
        rows = cursor.fetchall()
    finally:
        conn.close()

    if not rows:
        return {"success": True, "message": "No notes found to analyze", "populated": False}

    # Collect note summaries and entities
    summaries = []
    all_entities = []

    for row in rows:
        # Extract summary and entities from JSON payload
        if row["json_payload"]:
            try:
                payload = json.loads(row["json_payload"])
                summary = payload.get("summary", "")
                if summary:
                    summaries.append(summary)

                entities = payload.get("entities", [])
                for entity in entities:
                    entity_name = entity.get("name", "")
                    entity_type = entity.get("type", "")
                    if entity_name and entity_type:
                        all_entities.append(f"{entity_name} ({entity_type})")
            except json.JSONDecodeError:
                pass

    if not summaries:
        return {
            "success": True,
            "message": "No note summaries found to analyze",
            "populated": False,
        }

    # Prepare context for LLM
    notes_context = "\n\n".join(summaries[:30])  # Limit to avoid token overflow
    entities_context = ", ".join(list(set(all_entities))[:50])

    # Create prompt for LLM
    extraction_prompt = f"""Analyze these activity notes from a personal tracking app and extract information about the user.

ACTIVITY NOTES:
{notes_context}

DETECTED ENTITIES:
{entities_context}

Based on these notes, extract and return a JSON object with the following structure:
{{
    "interests": ["list of hobbies and interests you can infer"],
    "work_projects": ["list of work projects or tasks they seem to be working on"],
    "patterns": ["list of behavioral patterns you notice, e.g., 'Often works on coding projects in the afternoon'"],
    "facts": ["list of important facts about the user, e.g., 'Uses macOS', 'Programs in Python'"],
    "occupation_hint": "best guess at their occupation based on activity, or empty string if unclear"
}}

Be specific and factual. Only include things you can actually infer from the notes.
Return ONLY valid JSON, no other text."""

    # Call LLM
    client = OpenAI(api_key=api_key)
    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "system",
                    "content": "You are an assistant that extracts user information from activity notes. Return only valid JSON.",
                },
                {"role": "user", "content": extraction_prompt},
            ],
            temperature=0.3,
            max_tokens=1000,
        )

        result_text = response.choices[0].message.content or ""

        # Parse JSON from response
        # Handle potential markdown code blocks
        if "```json" in result_text:
            result_text = result_text.split("```json")[1].split("```")[0]
        elif "```" in result_text:
            result_text = result_text.split("```")[1].split("```")[0]

        extracted = json.loads(result_text.strip())

    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse LLM response: {e}")
        return {"success": False, "error": f"Failed to parse LLM response: {e}"}
    except Exception as e:
        logger.error(f"LLM call failed: {e}")
        return {"success": False, "error": str(e)}

    # Update memory with extracted information
    manager = get_memory_manager()
    memory = manager.get_memory()

    items_added = 0

    # Add interests
    for interest in extracted.get("interests", []):
        if interest and interest not in memory.interests:
            memory.interests.append(interest)
            items_added += 1

    # Add work projects
    for project in extracted.get("work_projects", []):
        if project and project not in memory.work_projects:
            memory.work_projects.append(project)
            items_added += 1

    # Add patterns
    for pattern in extracted.get("patterns", []):
        if pattern and pattern not in memory.learned_patterns:
            memory.learned_patterns.append(pattern)
            items_added += 1

    # Add facts
    for fact in extracted.get("facts", []):
        if fact and fact not in memory.important_facts:
            memory.important_facts.append(fact)
            items_added += 1

    # Update occupation if we got a hint and don't have one
    occupation_hint = extracted.get("occupation_hint", "")
    if occupation_hint and not memory.profile.occupation:
        memory.profile.occupation = occupation_hint
        items_added += 1

    # Save
    manager.save()

    logger.info(f"Memory population complete. Added {items_added} items.")

    return {
        "success": True,
        "populated": True,
        "notes_analyzed": len(rows),
        "items_added": items_added,
        "extracted": extracted,
    }


def is_memory_empty() -> bool:
    """Check if memory has any content."""
    memory = get_user_memory()
    return (
        not memory.profile.name
        and not memory.profile.occupation
        and not memory.interests
        and not memory.work_projects
        and not memory.learned_patterns
        and not memory.important_facts
    )


if __name__ == "__main__":
    import fire

    def show():
        """Show current memory."""
        manager = MemoryManager()
        memory = manager.load()
        return memory.to_dict()

    def raw():
        """Show raw markdown content."""
        manager = MemoryManager()
        manager.load()
        return manager._memory.to_markdown() if manager._memory else ""

    def update_profile(
        name: str = "", age: str = "", languages: str = "", location: str = "", occupation: str = ""
    ):
        """Update user profile."""
        manager = MemoryManager()
        manager.load()
        data = {}
        if name:
            data["name"] = name
        if age:
            data["age"] = age
        if languages:
            data["languages"] = languages
        if location:
            data["location"] = location
        if occupation:
            data["occupation"] = occupation
        return manager.update_profile(data)

    def add(section: str, item: str):
        """Add an item to a section (interests, preferences, facts, work, patterns)."""
        manager = MemoryManager()
        manager.load()

        section_lower = section.lower()
        if section_lower == "interest" or section_lower == "interests":
            return manager.add_interest(item)
        elif section_lower == "preference" or section_lower == "preferences":
            return manager.add_preference(item)
        elif section_lower == "fact" or section_lower == "facts":
            return manager.add_fact(item)
        elif section_lower == "work" or section_lower == "project":
            return manager.add_work_project(item)
        elif section_lower == "pattern" or section_lower == "patterns":
            return manager.add_pattern(item)
        elif section_lower == "insight" or section_lower == "insights":
            return manager.add_insight(item)
        else:
            return {"error": f"Unknown section: {section}"}

    def remove(section: str, item: str):
        """Remove an item from a section."""
        manager = MemoryManager()
        manager.load()
        return manager.remove_item(section, item)

    def context():
        """Get memory context for LLM."""
        return get_memory_context()

    def populate(max_notes: int = 50, force: bool = False):
        """Populate memory from existing notes using LLM."""
        if not force and not is_memory_empty():
            return {"message": "Memory already has content. Use --force to repopulate."}
        return populate_memory_from_notes(max_notes=max_notes)

    def is_empty():
        """Check if memory is empty."""
        return {"is_empty": is_memory_empty()}

    fire.Fire(
        {
            "show": show,
            "raw": raw,
            "profile": update_profile,
            "add": add,
            "remove": remove,
            "context": context,
            "populate": populate,
            "is_empty": is_empty,
        }
    )
