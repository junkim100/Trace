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

# Memory extraction model - use the best model for detailed extraction
MEMORY_EXTRACTION_MODEL = "gpt-5.2-2025-12-11"

# Default memory template - rich structure inspired by Claude Code and Mem0
DEFAULT_MEMORY_TEMPLATE = """# User Memory

> This file contains learned information about the user based on their activity.
> Updated automatically by Trace. Manual edits are preserved.

Last updated: {timestamp}

---

## Identity & Background

### Basic Profile
- **Name**:
- **Preferred Name/Nickname**:
- **Age/Generation**:
- **Location**:
- **Timezone**:
- **Languages**:

### Professional Identity
- **Current Role/Title**:
- **Company/Organization**:
- **Industry**:
- **Years of Experience**:
- **Career Stage**:

### Education & Expertise
- **Educational Background**:
- **Areas of Expertise**:
- **Certifications/Credentials**:

---

## Technical Profile

### Primary Tech Stack
_Technologies the user works with most frequently._

### Programming Languages
_Languages used, with proficiency indicators._

### Tools & Platforms
_Development tools, IDEs, platforms regularly used._

### Development Environment
_OS, hardware, development setup details._

---

## Current Focus

### Active Projects
_Projects currently being worked on with context and goals._

### Learning Goals
_Skills or technologies the user is actively learning._

### Ongoing Tasks
_Recurring tasks or responsibilities._

---

## Work Patterns & Habits

### Daily Rhythms
_When they typically work, peak productivity times._

### Work Style
_How they approach tasks, collaboration preferences._

### Communication Patterns
_Tools used, communication style, availability._

---

## Interests & Personal

### Professional Interests
_Topics of professional curiosity beyond current work._

### Personal Hobbies
_Non-work activities and interests._

### Media & Entertainment
_Music, podcasts, shows, games they enjoy._

---

## Preferences & Style

### Work Preferences
_Preferred approaches to tasks, meetings, collaboration._

### Technical Preferences
_Coding style, tool preferences, architectural opinions._

### Communication Style
_How they prefer to receive information._

---

## Relationships & Network

### Key People
_Important collaborators, mentors, teammates mentioned._

### Organizations
_Companies, communities, groups they're affiliated with._

---

## Important Context

### Key Facts
_Durable facts that affect how to assist them._

### Constraints & Considerations
_Limitations, preferences to always keep in mind._

### Goals & Aspirations
_Long-term professional and personal goals._

---

## Behavioral Insights

### Observed Patterns
_Patterns noticed from activity data._

### Productivity Indicators
_What conditions correlate with productive work._

---

## Memory Log

_Recent significant learnings about the user, with timestamps._

"""


@dataclass
class UserProfile:
    """User's comprehensive profile information."""

    # Basic Identity
    name: str = ""
    preferred_name: str = ""
    age: str = ""
    location: str = ""
    timezone: str = ""
    languages: str = ""

    # Professional Identity
    current_role: str = ""
    company: str = ""
    industry: str = ""
    years_experience: str = ""
    career_stage: str = ""

    # Education & Expertise
    education: str = ""
    expertise_areas: list[str] = field(default_factory=list)
    certifications: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "preferred_name": self.preferred_name,
            "age": self.age,
            "location": self.location,
            "timezone": self.timezone,
            "languages": self.languages,
            "current_role": self.current_role,
            "company": self.company,
            "industry": self.industry,
            "years_experience": self.years_experience,
            "career_stage": self.career_stage,
            "education": self.education,
            "expertise_areas": self.expertise_areas,
            "certifications": self.certifications,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "UserProfile":
        return cls(
            name=data.get("name", ""),
            preferred_name=data.get("preferred_name", ""),
            age=data.get("age", ""),
            location=data.get("location", ""),
            timezone=data.get("timezone", ""),
            languages=data.get("languages", ""),
            current_role=data.get("current_role", ""),
            company=data.get("company", ""),
            industry=data.get("industry", ""),
            years_experience=data.get("years_experience", ""),
            career_stage=data.get("career_stage", ""),
            education=data.get("education", ""),
            expertise_areas=data.get("expertise_areas", []),
            certifications=data.get("certifications", []),
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
class TechnicalProfile:
    """User's technical profile and stack."""

    primary_stack: list[str] = field(default_factory=list)
    programming_languages: list[str] = field(default_factory=list)
    tools_platforms: list[str] = field(default_factory=list)
    dev_environment: list[str] = field(default_factory=list)


@dataclass
class CurrentFocus:
    """User's current work focus."""

    active_projects: list[str] = field(default_factory=list)
    learning_goals: list[str] = field(default_factory=list)
    ongoing_tasks: list[str] = field(default_factory=list)


@dataclass
class WorkPatterns:
    """User's work patterns and habits."""

    daily_rhythms: list[str] = field(default_factory=list)
    work_style: list[str] = field(default_factory=list)
    communication_patterns: list[str] = field(default_factory=list)


@dataclass
class Interests:
    """User's interests."""

    professional: list[str] = field(default_factory=list)
    personal_hobbies: list[str] = field(default_factory=list)
    media_entertainment: list[str] = field(default_factory=list)


@dataclass
class Preferences:
    """User's preferences."""

    work_preferences: list[str] = field(default_factory=list)
    technical_preferences: list[str] = field(default_factory=list)
    communication_style: list[str] = field(default_factory=list)


@dataclass
class Relationships:
    """User's professional network."""

    key_people: list[str] = field(default_factory=list)
    organizations: list[str] = field(default_factory=list)


@dataclass
class ImportantContext:
    """Important context about the user."""

    key_facts: list[str] = field(default_factory=list)
    constraints: list[str] = field(default_factory=list)
    goals_aspirations: list[str] = field(default_factory=list)


@dataclass
class BehavioralInsights:
    """Behavioral patterns observed."""

    observed_patterns: list[str] = field(default_factory=list)
    productivity_indicators: list[str] = field(default_factory=list)


@dataclass
class MemoryLogEntry:
    """A timestamped memory log entry."""

    timestamp: datetime
    content: str
    category: str = ""


@dataclass
class UserMemory:
    """Complete user memory structure - comprehensive and detailed."""

    # Core profile
    profile: UserProfile = field(default_factory=UserProfile)

    # Technical profile
    technical: TechnicalProfile = field(default_factory=TechnicalProfile)

    # Current focus
    current_focus: CurrentFocus = field(default_factory=CurrentFocus)

    # Work patterns
    work_patterns: WorkPatterns = field(default_factory=WorkPatterns)

    # Interests
    interests: Interests = field(default_factory=Interests)

    # Preferences
    preferences: Preferences = field(default_factory=Preferences)

    # Relationships
    relationships: Relationships = field(default_factory=Relationships)

    # Important context
    context: ImportantContext = field(default_factory=ImportantContext)

    # Behavioral insights
    insights: BehavioralInsights = field(default_factory=BehavioralInsights)

    # Memory log for recent learnings
    memory_log: list[MemoryLogEntry] = field(default_factory=list)

    # Legacy fields for backward compatibility
    important_facts: list[str] = field(default_factory=list)
    conversation_insights: list[str] = field(default_factory=list)

    # Metadata
    last_updated: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "profile": self.profile.to_dict(),
            "technical": {
                "primary_stack": self.technical.primary_stack,
                "programming_languages": self.technical.programming_languages,
                "tools_platforms": self.technical.tools_platforms,
                "dev_environment": self.technical.dev_environment,
            },
            "current_focus": {
                "active_projects": self.current_focus.active_projects,
                "learning_goals": self.current_focus.learning_goals,
                "ongoing_tasks": self.current_focus.ongoing_tasks,
            },
            "work_patterns": {
                "daily_rhythms": self.work_patterns.daily_rhythms,
                "work_style": self.work_patterns.work_style,
                "communication_patterns": self.work_patterns.communication_patterns,
            },
            "interests": {
                "professional": self.interests.professional,
                "personal_hobbies": self.interests.personal_hobbies,
                "media_entertainment": self.interests.media_entertainment,
            },
            "preferences": {
                "work_preferences": self.preferences.work_preferences,
                "technical_preferences": self.preferences.technical_preferences,
                "communication_style": self.preferences.communication_style,
            },
            "relationships": {
                "key_people": self.relationships.key_people,
                "organizations": self.relationships.organizations,
            },
            "context": {
                "key_facts": self.context.key_facts,
                "constraints": self.context.constraints,
                "goals_aspirations": self.context.goals_aspirations,
            },
            "insights": {
                "observed_patterns": self.insights.observed_patterns,
                "productivity_indicators": self.insights.productivity_indicators,
            },
            "memory_log": [
                {"timestamp": e.timestamp.isoformat(), "content": e.content, "category": e.category}
                for e in self.memory_log[-20:]  # Keep last 20 entries
            ],
            "important_facts": self.important_facts,
            "conversation_insights": self.conversation_insights,
            "last_updated": self.last_updated.isoformat(),
        }

    def to_markdown(self) -> str:
        """Convert to rich markdown format."""

        def format_list(items: list[str], empty_msg: str = "") -> list[str]:
            """Format a list of items or return empty message."""
            if items:
                return [f"- {item}" for item in items]
            return [f"_{empty_msg}_"] if empty_msg else []

        lines = [
            "# User Memory",
            "",
            "> This file contains learned information about the user based on their activity.",
            "> Updated automatically by Trace. Manual edits are preserved.",
            ">",
            "> **Extraction Policy**: Only durable facts (likely true in 30+ days) are stored here.",
            "> Daily events and transient information stay in daily notes.",
            "",
            f"Last updated: {self.last_updated.strftime('%Y-%m-%d %H:%M:%S')}",
            "",
            "---",
            "",
            "## Identity & Background",
            "",
            "### Basic Profile",
            f"- **Name**: {self.profile.name}" if self.profile.name else "- **Name**:",
            f"- **Preferred Name/Nickname**: {self.profile.preferred_name}"
            if self.profile.preferred_name
            else "- **Preferred Name/Nickname**:",
            f"- **Age/Generation**: {self.profile.age}"
            if self.profile.age
            else "- **Age/Generation**:",
            f"- **Location**: {self.profile.location}"
            if self.profile.location
            else "- **Location**:",
            f"- **Timezone**: {self.profile.timezone}"
            if self.profile.timezone
            else "- **Timezone**:",
            f"- **Languages**: {self.profile.languages}"
            if self.profile.languages
            else "- **Languages**:",
            "",
            "### Professional Identity",
            f"- **Current Role/Title**: {self.profile.current_role}"
            if self.profile.current_role
            else "- **Current Role/Title**:",
            f"- **Company/Organization**: {self.profile.company}"
            if self.profile.company
            else "- **Company/Organization**:",
            f"- **Industry**: {self.profile.industry}"
            if self.profile.industry
            else "- **Industry**:",
            f"- **Years of Experience**: {self.profile.years_experience}"
            if self.profile.years_experience
            else "- **Years of Experience**:",
            f"- **Career Stage**: {self.profile.career_stage}"
            if self.profile.career_stage
            else "- **Career Stage**:",
            "",
            "### Education & Expertise",
            f"- **Educational Background**: {self.profile.education}"
            if self.profile.education
            else "- **Educational Background**:",
        ]

        # Add expertise areas
        if self.profile.expertise_areas:
            lines.append("- **Areas of Expertise**:")
            for area in self.profile.expertise_areas:
                lines.append(f"  - {area}")
        else:
            lines.append("- **Areas of Expertise**:")

        # Add certifications
        if self.profile.certifications:
            lines.append("- **Certifications/Credentials**:")
            for cert in self.profile.certifications:
                lines.append(f"  - {cert}")
        else:
            lines.append("- **Certifications/Credentials**:")

        lines.extend(
            [
                "",
                "---",
                "",
                "## Technical Profile",
                "",
                "### Primary Tech Stack",
            ]
        )
        lines.extend(
            format_list(
                self.technical.primary_stack,
                "Technologies will be learned from activity.",
            )
        )

        lines.extend(["", "### Programming Languages"])
        lines.extend(
            format_list(
                self.technical.programming_languages,
                "Languages will be detected from activity.",
            )
        )

        lines.extend(["", "### Tools & Platforms"])
        lines.extend(
            format_list(
                self.technical.tools_platforms,
                "Tools will be learned from app usage.",
            )
        )

        lines.extend(["", "### Development Environment"])
        lines.extend(
            format_list(
                self.technical.dev_environment,
                "Environment details will be detected.",
            )
        )

        lines.extend(
            [
                "",
                "---",
                "",
                "## Current Focus",
                "",
                "### Active Projects",
            ]
        )
        lines.extend(
            format_list(
                self.current_focus.active_projects,
                "Projects will be learned from activity.",
            )
        )

        lines.extend(["", "### Learning Goals"])
        lines.extend(
            format_list(
                self.current_focus.learning_goals,
                "Learning goals will be detected from activity.",
            )
        )

        lines.extend(["", "### Ongoing Tasks"])
        lines.extend(
            format_list(
                self.current_focus.ongoing_tasks,
                "Recurring tasks will be identified.",
            )
        )

        lines.extend(
            [
                "",
                "---",
                "",
                "## Work Patterns & Habits",
                "",
                "### Daily Rhythms",
            ]
        )
        lines.extend(
            format_list(
                self.work_patterns.daily_rhythms,
                "Work patterns will be learned over time.",
            )
        )

        lines.extend(["", "### Work Style"])
        lines.extend(
            format_list(
                self.work_patterns.work_style,
                "Work style will be observed.",
            )
        )

        lines.extend(["", "### Communication Patterns"])
        lines.extend(
            format_list(
                self.work_patterns.communication_patterns,
                "Communication patterns will be detected.",
            )
        )

        lines.extend(
            [
                "",
                "---",
                "",
                "## Interests & Personal",
                "",
                "### Professional Interests",
            ]
        )
        lines.extend(
            format_list(
                self.interests.professional,
                "Professional interests will be learned.",
            )
        )

        lines.extend(["", "### Personal Hobbies"])
        lines.extend(
            format_list(
                self.interests.personal_hobbies,
                "Hobbies will be detected from activity.",
            )
        )

        lines.extend(["", "### Media & Entertainment"])
        lines.extend(
            format_list(
                self.interests.media_entertainment,
                "Media preferences will be learned.",
            )
        )

        lines.extend(
            [
                "",
                "---",
                "",
                "## Preferences & Style",
                "",
                "### Work Preferences",
            ]
        )
        lines.extend(
            format_list(
                self.preferences.work_preferences,
                "Preferences will be learned.",
            )
        )

        lines.extend(["", "### Technical Preferences"])
        lines.extend(
            format_list(
                self.preferences.technical_preferences,
                "Technical preferences will be detected.",
            )
        )

        lines.extend(["", "### Communication Style"])
        lines.extend(
            format_list(
                self.preferences.communication_style,
                "Communication style will be observed.",
            )
        )

        lines.extend(
            [
                "",
                "---",
                "",
                "## Relationships & Network",
                "",
                "### Key People",
            ]
        )
        lines.extend(
            format_list(
                self.relationships.key_people,
                "Key collaborators will be identified.",
            )
        )

        lines.extend(["", "### Organizations"])
        lines.extend(
            format_list(
                self.relationships.organizations,
                "Organizations will be identified.",
            )
        )

        lines.extend(
            [
                "",
                "---",
                "",
                "## Important Context",
                "",
                "### Key Facts",
            ]
        )
        # Combine legacy facts with new structure
        all_facts = list(set(self.context.key_facts + self.important_facts))
        lines.extend(
            format_list(
                all_facts,
                "Key facts will be learned.",
            )
        )

        lines.extend(["", "### Constraints & Considerations"])
        lines.extend(
            format_list(
                self.context.constraints,
                "Constraints will be noted.",
            )
        )

        lines.extend(["", "### Goals & Aspirations"])
        lines.extend(
            format_list(
                self.context.goals_aspirations,
                "Goals will be identified from activity.",
            )
        )

        lines.extend(
            [
                "",
                "---",
                "",
                "## Behavioral Insights",
                "",
                "### Observed Patterns",
            ]
        )
        lines.extend(
            format_list(
                self.insights.observed_patterns,
                "Patterns will be learned over time.",
            )
        )

        lines.extend(["", "### Productivity Indicators"])
        lines.extend(
            format_list(
                self.insights.productivity_indicators,
                "Productivity patterns will be detected.",
            )
        )

        lines.extend(
            [
                "",
                "---",
                "",
                "## Memory Log",
                "",
            ]
        )
        if self.memory_log:
            for entry in self.memory_log[-10:]:  # Show last 10
                lines.append(f"- [{entry.timestamp.strftime('%Y-%m-%d %H:%M')}] {entry.content}")
        else:
            lines.append("_Recent learnings will appear here._")

        lines.append("")  # Final newline
        return "\n".join(lines)

    def get_context_for_llm(self) -> str:
        """Get a rich formatted context string for LLM prompts."""
        sections = []

        # Identity section
        identity_parts = []
        if self.profile.name:
            name = self.profile.preferred_name or self.profile.name
            identity_parts.append(f"Name: {name}")
        if self.profile.current_role and self.profile.company:
            identity_parts.append(f"Role: {self.profile.current_role} at {self.profile.company}")
        elif self.profile.current_role:
            identity_parts.append(f"Role: {self.profile.current_role}")
        if self.profile.location:
            identity_parts.append(f"Location: {self.profile.location}")
        if self.profile.languages:
            identity_parts.append(f"Languages: {self.profile.languages}")
        if identity_parts:
            sections.append("**Identity**: " + " | ".join(identity_parts))

        # Expertise section
        expertise_parts = []
        if self.profile.expertise_areas:
            expertise_parts.extend(self.profile.expertise_areas[:3])
        if self.technical.programming_languages:
            expertise_parts.append(
                f"Codes in {', '.join(self.technical.programming_languages[:4])}"
            )
        if expertise_parts:
            sections.append("**Expertise**: " + "; ".join(expertise_parts))

        # Tech stack
        if self.technical.primary_stack:
            sections.append("**Tech Stack**: " + ", ".join(self.technical.primary_stack[:5]))

        # Current focus
        focus_parts = []
        if self.current_focus.active_projects:
            focus_parts.append("Projects: " + ", ".join(self.current_focus.active_projects[:3]))
        if self.current_focus.learning_goals:
            focus_parts.append("Learning: " + ", ".join(self.current_focus.learning_goals[:2]))
        if focus_parts:
            sections.append("**Current Focus**: " + " | ".join(focus_parts))

        # Work patterns
        if self.work_patterns.daily_rhythms:
            sections.append("**Work Patterns**: " + "; ".join(self.work_patterns.daily_rhythms[:2]))

        # Interests
        all_interests = self.interests.professional + self.interests.personal_hobbies
        if all_interests:
            sections.append("**Interests**: " + ", ".join(all_interests[:5]))

        # Preferences
        all_prefs = self.preferences.technical_preferences + self.preferences.work_preferences
        if all_prefs:
            sections.append("**Preferences**: " + "; ".join(all_prefs[:3]))

        # Key facts
        all_facts = self.context.key_facts + self.important_facts
        if all_facts:
            sections.append("**Key Facts**: " + "; ".join(all_facts[:4]))

        # Goals
        if self.context.goals_aspirations:
            sections.append("**Goals**: " + "; ".join(self.context.goals_aspirations[:2]))

        # Key people
        if self.relationships.key_people:
            sections.append("**Key People**: " + ", ".join(self.relationships.key_people[:4]))

        if not sections:
            return ""

        return "## User Context\n\n" + "\n".join(f"- {s}" for s in sections)


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

    def update_profile(self, profile_data: dict[str, Any]) -> bool:
        """
        Update user profile with comprehensive fields.

        Args:
            profile_data: Dictionary with profile fields

        Returns:
            True if saved successfully
        """
        memory = self.get_memory()

        # Basic identity
        if "name" in profile_data:
            memory.profile.name = profile_data["name"]
        if "preferred_name" in profile_data:
            memory.profile.preferred_name = profile_data["preferred_name"]
        if "age" in profile_data:
            memory.profile.age = profile_data["age"]
        if "location" in profile_data:
            memory.profile.location = profile_data["location"]
        if "timezone" in profile_data:
            memory.profile.timezone = profile_data["timezone"]
        if "languages" in profile_data:
            memory.profile.languages = profile_data["languages"]

        # Professional identity
        if "current_role" in profile_data:
            memory.profile.current_role = profile_data["current_role"]
        if "occupation" in profile_data:  # Legacy support
            memory.profile.current_role = profile_data["occupation"]
        if "company" in profile_data:
            memory.profile.company = profile_data["company"]
        if "industry" in profile_data:
            memory.profile.industry = profile_data["industry"]
        if "years_experience" in profile_data:
            memory.profile.years_experience = profile_data["years_experience"]
        if "career_stage" in profile_data:
            memory.profile.career_stage = profile_data["career_stage"]

        # Education & expertise
        if "education" in profile_data:
            memory.profile.education = profile_data["education"]
        if "expertise_areas" in profile_data and isinstance(profile_data["expertise_areas"], list):
            for area in profile_data["expertise_areas"]:
                if area and area not in memory.profile.expertise_areas:
                    memory.profile.expertise_areas.append(area)
        if "certifications" in profile_data and isinstance(profile_data["certifications"], list):
            for cert in profile_data["certifications"]:
                if cert and cert not in memory.profile.certifications:
                    memory.profile.certifications.append(cert)

        return self.save()

    def add_interest(self, interest: str, category: str = "personal") -> bool:
        """Add an interest (personal or professional)."""
        memory = self.get_memory()
        target = (
            memory.interests.professional
            if category == "professional"
            else memory.interests.personal_hobbies
        )
        if interest and interest not in target:
            target.append(interest)
            return self.save()
        return True

    def add_preference(self, preference: str, category: str = "work") -> bool:
        """Add a preference (work, technical, or communication)."""
        memory = self.get_memory()
        if category == "technical":
            target = memory.preferences.technical_preferences
        elif category == "communication":
            target = memory.preferences.communication_style
        else:
            target = memory.preferences.work_preferences
        if preference and preference not in target:
            target.append(preference)
            return self.save()
        return True

    def add_fact(self, fact: str) -> bool:
        """Add an important fact."""
        memory = self.get_memory()
        # Add to both legacy and new structure
        if fact and fact not in memory.context.key_facts:
            memory.context.key_facts.append(fact)
        if fact and fact not in memory.important_facts:
            memory.important_facts.append(fact)
            return self.save()
        return True

    def add_work_project(self, project: str) -> bool:
        """Add a work/project item."""
        memory = self.get_memory()
        if project and project not in memory.current_focus.active_projects:
            memory.current_focus.active_projects.append(project)
            return self.save()
        return True

    def add_pattern(self, pattern: str) -> bool:
        """Add a learned/observed pattern."""
        memory = self.get_memory()
        if pattern and pattern not in memory.insights.observed_patterns:
            memory.insights.observed_patterns.append(pattern)
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

    def add_memory_log_entry(self, content: str, category: str = "") -> bool:
        """Add an entry to the memory log."""
        memory = self.get_memory()
        memory.memory_log.append(
            MemoryLogEntry(timestamp=datetime.now(), content=content, category=category)
        )
        # Keep only last 50 log entries
        if len(memory.memory_log) > 50:
            memory.memory_log = memory.memory_log[-50:]
        return self.save()

    def remove_item(self, section: str, item: str) -> bool:
        """
        Remove an item from a section.

        Args:
            section: Section name
            item: Item to remove

        Returns:
            True if saved successfully
        """
        memory = self.get_memory()

        # Map section names to their corresponding lists
        section_map = {
            # Legacy mappings
            "interests": memory.interests.personal_hobbies,
            "preferences": memory.preferences.work_preferences,
            "facts": memory.context.key_facts,
            "important_facts": memory.important_facts,
            "work": memory.current_focus.active_projects,
            "work_projects": memory.current_focus.active_projects,
            "patterns": memory.insights.observed_patterns,
            "learned_patterns": memory.insights.observed_patterns,
            "insights": memory.conversation_insights,
            "conversation_insights": memory.conversation_insights,
            # New structure mappings
            "professional_interests": memory.interests.professional,
            "personal_hobbies": memory.interests.personal_hobbies,
            "media_entertainment": memory.interests.media_entertainment,
            "primary_stack": memory.technical.primary_stack,
            "programming_languages": memory.technical.programming_languages,
            "tools_platforms": memory.technical.tools_platforms,
            "dev_environment": memory.technical.dev_environment,
            "active_projects": memory.current_focus.active_projects,
            "learning_goals": memory.current_focus.learning_goals,
            "ongoing_tasks": memory.current_focus.ongoing_tasks,
            "daily_rhythms": memory.work_patterns.daily_rhythms,
            "work_style": memory.work_patterns.work_style,
            "communication_patterns": memory.work_patterns.communication_patterns,
            "work_preferences": memory.preferences.work_preferences,
            "technical_preferences": memory.preferences.technical_preferences,
            "communication_style": memory.preferences.communication_style,
            "key_people": memory.relationships.key_people,
            "organizations": memory.relationships.organizations,
            "key_facts": memory.context.key_facts,
            "constraints": memory.context.constraints,
            "goals_aspirations": memory.context.goals_aspirations,
            "observed_patterns": memory.insights.observed_patterns,
            "productivity_indicators": memory.insights.productivity_indicators,
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

        def add_to_list(target: list, items: list | None) -> None:
            if items:
                for item in items:
                    if item and item not in target:
                        target.append(item)

        # Profile updates
        if "profile" in updates and isinstance(updates["profile"], dict):
            self.update_profile(updates["profile"])

        # Technical updates
        if "technical" in updates and isinstance(updates["technical"], dict):
            tech = updates["technical"]
            add_to_list(memory.technical.primary_stack, tech.get("primary_stack"))
            add_to_list(memory.technical.programming_languages, tech.get("programming_languages"))
            add_to_list(memory.technical.tools_platforms, tech.get("tools_platforms"))
            add_to_list(memory.technical.dev_environment, tech.get("dev_environment"))

        # Current focus updates
        if "current_focus" in updates and isinstance(updates["current_focus"], dict):
            focus = updates["current_focus"]
            add_to_list(memory.current_focus.active_projects, focus.get("active_projects"))
            add_to_list(memory.current_focus.learning_goals, focus.get("learning_goals"))
            add_to_list(memory.current_focus.ongoing_tasks, focus.get("ongoing_tasks"))

        # Work patterns updates
        if "work_patterns" in updates and isinstance(updates["work_patterns"], dict):
            patterns = updates["work_patterns"]
            add_to_list(memory.work_patterns.daily_rhythms, patterns.get("daily_rhythms"))
            add_to_list(memory.work_patterns.work_style, patterns.get("work_style"))
            add_to_list(
                memory.work_patterns.communication_patterns, patterns.get("communication_patterns")
            )

        # Interests updates
        if "interests" in updates:
            if isinstance(updates["interests"], dict):
                interests = updates["interests"]
                add_to_list(memory.interests.professional, interests.get("professional"))
                add_to_list(memory.interests.personal_hobbies, interests.get("personal_hobbies"))
                add_to_list(
                    memory.interests.media_entertainment, interests.get("media_entertainment")
                )
            elif isinstance(updates["interests"], list):
                # Legacy format - add to personal hobbies
                add_to_list(memory.interests.personal_hobbies, updates["interests"])

        # Preferences updates
        if "preferences" in updates:
            if isinstance(updates["preferences"], dict):
                prefs = updates["preferences"]
                add_to_list(memory.preferences.work_preferences, prefs.get("work_preferences"))
                add_to_list(
                    memory.preferences.technical_preferences, prefs.get("technical_preferences")
                )
                add_to_list(
                    memory.preferences.communication_style, prefs.get("communication_style")
                )
            elif isinstance(updates["preferences"], list):
                # Legacy format
                add_to_list(memory.preferences.work_preferences, updates["preferences"])

        # Relationships updates
        if "relationships" in updates and isinstance(updates["relationships"], dict):
            rel = updates["relationships"]
            add_to_list(memory.relationships.key_people, rel.get("key_people"))
            add_to_list(memory.relationships.organizations, rel.get("organizations"))

        # Context updates
        if "context" in updates and isinstance(updates["context"], dict):
            ctx = updates["context"]
            add_to_list(memory.context.key_facts, ctx.get("key_facts"))
            add_to_list(memory.context.constraints, ctx.get("constraints"))
            add_to_list(memory.context.goals_aspirations, ctx.get("goals_aspirations"))

        # Insights updates
        if "insights" in updates and isinstance(updates["insights"], dict):
            ins = updates["insights"]
            add_to_list(memory.insights.observed_patterns, ins.get("observed_patterns"))
            add_to_list(memory.insights.productivity_indicators, ins.get("productivity_indicators"))

        # Legacy format support
        if "facts" in updates or "important_facts" in updates:
            facts = updates.get("facts") or updates.get("important_facts") or []
            if isinstance(facts, list):
                add_to_list(memory.context.key_facts, facts)
                add_to_list(memory.important_facts, facts)

        if "work" in updates or "work_projects" in updates:
            work = updates.get("work") or updates.get("work_projects") or []
            if isinstance(work, list):
                add_to_list(memory.current_focus.active_projects, work)

        if "patterns" in updates or "learned_patterns" in updates:
            patterns = updates.get("patterns") or updates.get("learned_patterns") or []
            if isinstance(patterns, list):
                add_to_list(memory.insights.observed_patterns, patterns)

        if "conversation_insights" in updates:
            insights = updates.get("conversation_insights") or []
            if isinstance(insights, list):
                for insight in insights:
                    self.add_insight(insight)

        return self.save()

    def _parse_markdown(self, content: str) -> UserMemory:
        """
        Parse rich markdown content into UserMemory.

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

        def extract_field(pattern: str, text: str) -> str:
            """Extract a single field value."""
            match = re.search(pattern, text)
            return match.group(1).strip() if match else ""

        def extract_list_after_heading(heading: str, text: str) -> list[str]:
            """Extract list items after a ### heading."""
            pattern = rf"### {re.escape(heading)}\s*\n(.*?)(?=\n### |\n---|\Z)"
            match = re.search(pattern, text, re.DOTALL)
            if not match:
                return []
            section = match.group(1)
            items = []
            for line in section.split("\n"):
                line = line.strip()
                if line.startswith("- ") and not line.startswith("_"):
                    # Handle both "- item" and "- [timestamp] item" formats
                    item = line[2:].strip()
                    if item and not item.startswith("**"):  # Skip field definitions
                        items.append(item)
                elif line.startswith("  - "):  # Nested items
                    item = line[4:].strip()
                    if item:
                        items.append(item)
            return items

        # Parse Basic Profile
        memory.profile.name = extract_field(r"\*\*Name\*\*:\s*(.+)", content)
        memory.profile.preferred_name = extract_field(
            r"\*\*Preferred Name/Nickname\*\*:\s*(.+)", content
        )
        memory.profile.age = extract_field(r"\*\*Age/Generation\*\*:\s*(.+)", content)
        memory.profile.location = extract_field(r"\*\*Location\*\*:\s*([^\n]+)", content)
        memory.profile.timezone = extract_field(r"\*\*Timezone\*\*:\s*(.+)", content)
        memory.profile.languages = extract_field(r"\*\*Languages\*\*:\s*(.+)", content)

        # Parse Professional Identity
        memory.profile.current_role = extract_field(r"\*\*Current Role/Title\*\*:\s*(.+)", content)
        memory.profile.company = extract_field(r"\*\*Company/Organization\*\*:\s*(.+)", content)
        memory.profile.industry = extract_field(r"\*\*Industry\*\*:\s*(.+)", content)
        memory.profile.years_experience = extract_field(
            r"\*\*Years of Experience\*\*:\s*(.+)", content
        )
        memory.profile.career_stage = extract_field(r"\*\*Career Stage\*\*:\s*(.+)", content)

        # Parse Education & Expertise
        memory.profile.education = extract_field(r"\*\*Educational Background\*\*:\s*(.+)", content)

        # Extract expertise areas (nested list under Areas of Expertise)
        expertise_match = re.search(r"\*\*Areas of Expertise\*\*:\s*\n((?:\s+-\s+.+\n?)*)", content)
        if expertise_match:
            for line in expertise_match.group(1).split("\n"):
                line = line.strip()
                if line.startswith("- "):
                    memory.profile.expertise_areas.append(line[2:].strip())

        # Parse Technical Profile
        memory.technical.primary_stack = extract_list_after_heading("Primary Tech Stack", content)
        memory.technical.programming_languages = extract_list_after_heading(
            "Programming Languages", content
        )
        memory.technical.tools_platforms = extract_list_after_heading("Tools & Platforms", content)
        memory.technical.dev_environment = extract_list_after_heading(
            "Development Environment", content
        )

        # Parse Current Focus
        memory.current_focus.active_projects = extract_list_after_heading(
            "Active Projects", content
        )
        memory.current_focus.learning_goals = extract_list_after_heading("Learning Goals", content)
        memory.current_focus.ongoing_tasks = extract_list_after_heading("Ongoing Tasks", content)

        # Parse Work Patterns
        memory.work_patterns.daily_rhythms = extract_list_after_heading("Daily Rhythms", content)
        memory.work_patterns.work_style = extract_list_after_heading("Work Style", content)
        memory.work_patterns.communication_patterns = extract_list_after_heading(
            "Communication Patterns", content
        )

        # Parse Interests
        memory.interests.professional = extract_list_after_heading(
            "Professional Interests", content
        )
        memory.interests.personal_hobbies = extract_list_after_heading("Personal Hobbies", content)
        memory.interests.media_entertainment = extract_list_after_heading(
            "Media & Entertainment", content
        )

        # Parse Preferences
        memory.preferences.work_preferences = extract_list_after_heading(
            "Work Preferences", content
        )
        memory.preferences.technical_preferences = extract_list_after_heading(
            "Technical Preferences", content
        )
        memory.preferences.communication_style = extract_list_after_heading(
            "Communication Style", content
        )

        # Parse Relationships
        memory.relationships.key_people = extract_list_after_heading("Key People", content)
        memory.relationships.organizations = extract_list_after_heading("Organizations", content)

        # Parse Important Context
        memory.context.key_facts = extract_list_after_heading("Key Facts", content)
        memory.context.constraints = extract_list_after_heading(
            "Constraints & Considerations", content
        )
        memory.context.goals_aspirations = extract_list_after_heading(
            "Goals & Aspirations", content
        )

        # Parse Behavioral Insights
        memory.insights.observed_patterns = extract_list_after_heading("Observed Patterns", content)
        memory.insights.productivity_indicators = extract_list_after_heading(
            "Productivity Indicators", content
        )

        # Parse Memory Log
        log_match = re.search(r"## Memory Log\s*\n(.*?)(?=\n---|\Z)", content, re.DOTALL)
        if log_match:
            for line in log_match.group(1).split("\n"):
                line = line.strip()
                # Format: - [2024-01-15 10:30] Content here
                log_entry_match = re.match(
                    r"-\s*\[(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2})\]\s*(.+)", line
                )
                if log_entry_match:
                    try:
                        ts = datetime.strptime(log_entry_match.group(1), "%Y-%m-%d %H:%M")
                        memory.memory_log.append(
                            MemoryLogEntry(timestamp=ts, content=log_entry_match.group(2))
                        )
                    except ValueError:
                        pass

        # Legacy support: also check old format sections
        legacy_interests = extract_list_after_heading("Interests & Hobbies", content)
        if legacy_interests:
            memory.interests.personal_hobbies.extend(
                i for i in legacy_interests if i not in memory.interests.personal_hobbies
            )

        legacy_prefs = extract_list_after_heading("Preferences", content)
        if legacy_prefs:
            memory.preferences.work_preferences.extend(
                p for p in legacy_prefs if p not in memory.preferences.work_preferences
            )

        memory.important_facts = extract_list_after_heading("Important Facts", content)
        memory.conversation_insights = extract_list_after_heading("Conversation Insights", content)

        # Legacy: Work & Projects -> active_projects
        legacy_work = extract_list_after_heading("Work & Projects", content)
        if legacy_work:
            memory.current_focus.active_projects.extend(
                w for w in legacy_work if w not in memory.current_focus.active_projects
            )

        # Legacy: Learned Patterns -> observed_patterns
        legacy_patterns = extract_list_after_heading("Learned Patterns", content)
        if legacy_patterns:
            memory.insights.observed_patterns.extend(
                p for p in legacy_patterns if p not in memory.insights.observed_patterns
            )

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


def populate_memory_from_notes(api_key: str | None = None, max_notes: int = 100) -> dict:
    """
    Populate memory by analyzing existing notes using advanced multi-pass extraction.

    Uses sophisticated prompting techniques inspired by Claude Code, Mem0, and
    OpenAI's context engineering best practices. Extracts detailed, typed user
    information across multiple dimensions.

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

    logger.info("Starting comprehensive memory population from notes...")

    # Get API key
    if not api_key:
        api_key = get_api_key()
    if not api_key:
        return {"success": False, "error": "No API key available"}

    # Get notes from database with more context
    conn = get_connection(DB_PATH)
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT note_id, note_type, start_ts, json_payload
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

    # Collect comprehensive note data
    note_entries = []
    all_entities = []
    all_apps = set()
    all_domains = set()
    timestamps = []

    for row in rows:
        if row["json_payload"]:
            try:
                payload = json.loads(row["json_payload"])
                summary = payload.get("summary", "")
                if summary:
                    # Include timestamp for temporal analysis
                    ts = row["start_ts"] if row["start_ts"] else ""
                    note_entries.append(
                        {"timestamp": ts, "summary": summary, "type": row["note_type"]}
                    )
                    if ts:
                        timestamps.append(ts)

                # Collect entities with types
                entities = payload.get("entities", [])
                for entity in entities:
                    entity_name = entity.get("name", "")
                    entity_type = entity.get("type", "")
                    if entity_name and entity_type:
                        all_entities.append({"name": entity_name, "type": entity_type})
                        if entity_type.lower() == "app":
                            all_apps.add(entity_name)
                        elif entity_type.lower() == "domain":
                            all_domains.add(entity_name)
            except json.JSONDecodeError:
                pass

    if not note_entries:
        return {
            "success": True,
            "message": "No note summaries found to analyze",
            "populated": False,
        }

    # Prepare rich context for LLM
    # Format notes with timestamps for temporal pattern detection
    formatted_notes = []
    for entry in note_entries[:60]:  # More notes for better analysis
        ts_str = entry["timestamp"][:16] if entry["timestamp"] else "Unknown time"
        formatted_notes.append(f"[{ts_str}] {entry['summary']}")

    notes_context = "\n\n".join(formatted_notes)

    # Group entities by type for better extraction
    entity_groups = {}
    for e in all_entities:
        etype = e["type"]
        if etype not in entity_groups:
            entity_groups[etype] = set()
        entity_groups[etype].add(e["name"])

    entities_formatted = []
    for etype, names in entity_groups.items():
        names_list = list(names)[:15]  # Limit per type
        entities_formatted.append(f"{etype}: {', '.join(names_list)}")
    entities_context = "\n".join(entities_formatted)

    # Multi-pass extraction using the best model
    client = OpenAI(api_key=api_key)

    # ===== PASS 1: Deep Profile & Identity Extraction =====
    profile_prompt = f"""You are an expert user profiler analyzing activity data from a personal tracking app.
Your task is to build a comprehensive understanding of who this user is based on their digital activity.

ACTIVITY NOTES (with timestamps):
{notes_context}

DETECTED ENTITIES BY TYPE:
{entities_context}

APPS FREQUENTLY USED: {", ".join(list(all_apps)[:20])}
DOMAINS VISITED: {", ".join(list(all_domains)[:20])}

---

## Extraction Guidelines

Follow these principles from state-of-the-art memory systems:

1. **Be Specific, Not Generic**: Extract concrete, actionable information. "Uses Python for data analysis" is better than "Programs in Python".

2. **Durable Facts Only**: Only extract information that is likely to remain true. Avoid one-time events unless highly significant.

3. **Explicit Over Inferred**: Prioritize clearly stated or demonstrated information. Mark uncertainty when inferring.

4. **Typed Traits**: Classify each piece of information appropriately.

5. **Temporal Awareness**: Note patterns in when things happen (morning person, weekend coder, etc.)

---

## Required Output

Analyze the data and return a JSON object with this EXACT structure:

```json
{{
    "profile": {{
        "name": "extracted name or empty string",
        "preferred_name": "nickname if detected or empty",
        "age_generation": "age or generation (Gen Z, Millennial, etc.) if detectable",
        "location": "city/country if mentioned",
        "timezone": "inferred timezone from activity patterns",
        "languages": "spoken/written languages detected",
        "current_role": "job title/role if clear",
        "company": "company/organization name if mentioned",
        "industry": "industry/field they work in",
        "years_experience": "experience level if detectable (junior/mid/senior or years)",
        "career_stage": "career stage (student/early-career/mid-career/senior/executive)",
        "education": "educational background if mentioned",
        "expertise_areas": ["list of areas of expertise demonstrated"]
    }},
    "technical": {{
        "primary_stack": ["main technologies they work with - be specific (e.g., 'React with TypeScript' not just 'JavaScript')"],
        "programming_languages": ["languages with proficiency notes, e.g., 'Python (primary)', 'JavaScript (proficient)'"],
        "tools_platforms": ["specific tools: IDEs, services, platforms used regularly"],
        "dev_environment": ["OS, hardware, setup details detected"]
    }},
    "current_focus": {{
        "active_projects": ["current projects with context, e.g., 'Building Trace - a macOS activity tracking app'"],
        "learning_goals": ["what they're actively learning or exploring"],
        "ongoing_tasks": ["recurring responsibilities or tasks"]
    }},
    "work_patterns": {{
        "daily_rhythms": ["when they typically work, e.g., 'Most productive 9am-12pm', 'Often works late evenings'"],
        "work_style": ["how they approach work, e.g., 'Deep focus sessions', 'Frequent context switching'"],
        "communication_patterns": ["tools used, style, availability patterns"]
    }},
    "interests": {{
        "professional": ["professional topics of interest beyond core work"],
        "personal_hobbies": ["non-work activities, hobbies, pastimes"],
        "media_entertainment": ["music, podcasts, shows, games they enjoy"]
    }},
    "preferences": {{
        "work_preferences": ["how they prefer to work"],
        "technical_preferences": ["coding style, tool preferences, architectural opinions"],
        "communication_style": ["how they communicate and prefer to receive info"]
    }},
    "relationships": {{
        "key_people": ["important collaborators, frequently mentioned people with context"],
        "organizations": ["companies, communities, groups they're affiliated with"]
    }},
    "context": {{
        "key_facts": ["durable important facts that affect how to assist them"],
        "constraints": ["limitations or considerations to keep in mind"],
        "goals_aspirations": ["long-term goals mentioned or implied"]
    }},
    "insights": {{
        "observed_patterns": ["behavioral patterns from the data"],
        "productivity_indicators": ["what correlates with productive work"]
    }}
}}
```

IMPORTANT RULES:
- Return ONLY valid JSON, no other text or markdown code fences
- Use empty strings "" for unknown single values
- Use empty arrays [] for unknown list values
- Be detailed and specific - this memory will be used to personalize assistance
- Include reasoning in the values where helpful, e.g., "Python (primary language, used in 80% of coding sessions)"
- For lists, aim for 3-10 high-quality items per category when evidence supports it"""

    try:
        logger.info("Running deep memory extraction with gpt-5.2...")
        response = client.chat.completions.create(
            model=MEMORY_EXTRACTION_MODEL,
            messages=[
                {
                    "role": "system",
                    "content": """You are an expert user profiler and memory extraction system.
Your goal is to build a comprehensive, accurate understanding of users from their activity data.

Key principles:
- Extract SPECIFIC, ACTIONABLE information (not generic observations)
- Only include DURABLE facts (things likely to remain true)
- Prefer EXPLICIT information over speculation
- Include CONTEXT with each item to make it actionable
- Be THOROUGH - this memory enables personalized assistance

You must return valid JSON matching the exact schema requested.""",
                },
                {"role": "user", "content": profile_prompt},
            ],
            temperature=0.2,  # Lower temp for factual extraction
            max_completion_tokens=4000,  # Use max_completion_tokens for newer models
        )

        result_text = response.choices[0].message.content or ""

        # Parse JSON from response (handle potential markdown fences)
        if "```json" in result_text:
            result_text = result_text.split("```json")[1].split("```")[0]
        elif "```" in result_text:
            result_text = result_text.split("```")[1].split("```")[0]

        extracted = json.loads(result_text.strip())

    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse LLM response: {e}")
        logger.error(f"Response was: {result_text[:500]}...")
        return {"success": False, "error": f"Failed to parse LLM response: {e}"}
    except Exception as e:
        logger.error(f"LLM call failed: {e}")
        return {"success": False, "error": str(e)}

    # ===== Apply Extracted Data to Memory =====
    manager = get_memory_manager()
    memory = manager.get_memory()

    items_added = 0

    # Helper to add items to lists without duplicates
    def add_to_list(target: list, items: list, dedupe: bool = True) -> int:
        added = 0
        for item in items or []:
            if item and (not dedupe or item not in target):
                target.append(item)
                added += 1
        return added

    # Apply profile data
    profile_data = extracted.get("profile", {})
    if profile_data.get("name") and not memory.profile.name:
        memory.profile.name = profile_data["name"]
        items_added += 1
    if profile_data.get("preferred_name") and not memory.profile.preferred_name:
        memory.profile.preferred_name = profile_data["preferred_name"]
        items_added += 1
    if profile_data.get("age_generation") and not memory.profile.age:
        memory.profile.age = profile_data["age_generation"]
        items_added += 1
    if profile_data.get("location") and not memory.profile.location:
        memory.profile.location = profile_data["location"]
        items_added += 1
    if profile_data.get("timezone") and not memory.profile.timezone:
        memory.profile.timezone = profile_data["timezone"]
        items_added += 1
    if profile_data.get("languages") and not memory.profile.languages:
        memory.profile.languages = profile_data["languages"]
        items_added += 1
    if profile_data.get("current_role") and not memory.profile.current_role:
        memory.profile.current_role = profile_data["current_role"]
        items_added += 1
    if profile_data.get("company") and not memory.profile.company:
        memory.profile.company = profile_data["company"]
        items_added += 1
    if profile_data.get("industry") and not memory.profile.industry:
        memory.profile.industry = profile_data["industry"]
        items_added += 1
    if profile_data.get("years_experience") and not memory.profile.years_experience:
        memory.profile.years_experience = profile_data["years_experience"]
        items_added += 1
    if profile_data.get("career_stage") and not memory.profile.career_stage:
        memory.profile.career_stage = profile_data["career_stage"]
        items_added += 1
    if profile_data.get("education") and not memory.profile.education:
        memory.profile.education = profile_data["education"]
        items_added += 1

    items_added += add_to_list(
        memory.profile.expertise_areas, profile_data.get("expertise_areas", [])
    )

    # Apply technical data
    tech_data = extracted.get("technical", {})
    items_added += add_to_list(memory.technical.primary_stack, tech_data.get("primary_stack", []))
    items_added += add_to_list(
        memory.technical.programming_languages, tech_data.get("programming_languages", [])
    )
    items_added += add_to_list(
        memory.technical.tools_platforms, tech_data.get("tools_platforms", [])
    )
    items_added += add_to_list(
        memory.technical.dev_environment, tech_data.get("dev_environment", [])
    )

    # Apply current focus
    focus_data = extracted.get("current_focus", {})
    items_added += add_to_list(
        memory.current_focus.active_projects, focus_data.get("active_projects", [])
    )
    items_added += add_to_list(
        memory.current_focus.learning_goals, focus_data.get("learning_goals", [])
    )
    items_added += add_to_list(
        memory.current_focus.ongoing_tasks, focus_data.get("ongoing_tasks", [])
    )

    # Apply work patterns
    patterns_data = extracted.get("work_patterns", {})
    items_added += add_to_list(
        memory.work_patterns.daily_rhythms, patterns_data.get("daily_rhythms", [])
    )
    items_added += add_to_list(memory.work_patterns.work_style, patterns_data.get("work_style", []))
    items_added += add_to_list(
        memory.work_patterns.communication_patterns, patterns_data.get("communication_patterns", [])
    )

    # Apply interests
    interests_data = extracted.get("interests", {})
    items_added += add_to_list(
        memory.interests.professional, interests_data.get("professional", [])
    )
    items_added += add_to_list(
        memory.interests.personal_hobbies, interests_data.get("personal_hobbies", [])
    )
    items_added += add_to_list(
        memory.interests.media_entertainment, interests_data.get("media_entertainment", [])
    )

    # Apply preferences
    prefs_data = extracted.get("preferences", {})
    items_added += add_to_list(
        memory.preferences.work_preferences, prefs_data.get("work_preferences", [])
    )
    items_added += add_to_list(
        memory.preferences.technical_preferences, prefs_data.get("technical_preferences", [])
    )
    items_added += add_to_list(
        memory.preferences.communication_style, prefs_data.get("communication_style", [])
    )

    # Apply relationships
    rel_data = extracted.get("relationships", {})
    items_added += add_to_list(memory.relationships.key_people, rel_data.get("key_people", []))
    items_added += add_to_list(
        memory.relationships.organizations, rel_data.get("organizations", [])
    )

    # Apply context
    ctx_data = extracted.get("context", {})
    items_added += add_to_list(memory.context.key_facts, ctx_data.get("key_facts", []))
    items_added += add_to_list(memory.context.constraints, ctx_data.get("constraints", []))
    items_added += add_to_list(
        memory.context.goals_aspirations, ctx_data.get("goals_aspirations", [])
    )

    # Apply insights
    insights_data = extracted.get("insights", {})
    items_added += add_to_list(
        memory.insights.observed_patterns, insights_data.get("observed_patterns", [])
    )
    items_added += add_to_list(
        memory.insights.productivity_indicators, insights_data.get("productivity_indicators", [])
    )

    # Add memory log entry
    memory.memory_log.append(
        MemoryLogEntry(
            timestamp=datetime.now(),
            content=f"Initial memory population from {len(note_entries)} activity notes",
            category="system",
        )
    )

    # Save
    manager.save()

    logger.info(
        f"Memory population complete. Added {items_added} items from {len(note_entries)} notes."
    )

    return {
        "success": True,
        "populated": True,
        "notes_analyzed": len(note_entries),
        "items_added": items_added,
        "model_used": MEMORY_EXTRACTION_MODEL,
        "extracted": extracted,
    }


def is_memory_empty() -> bool:
    """Check if memory has any meaningful content."""
    memory = get_user_memory()

    # Check profile fields
    has_profile = any(
        [
            memory.profile.name,
            memory.profile.current_role,
            memory.profile.company,
            memory.profile.expertise_areas,
        ]
    )

    # Check technical profile
    has_technical = any(
        [
            memory.technical.primary_stack,
            memory.technical.programming_languages,
            memory.technical.tools_platforms,
        ]
    )

    # Check current focus
    has_focus = any(
        [
            memory.current_focus.active_projects,
            memory.current_focus.learning_goals,
        ]
    )

    # Check interests
    has_interests = any(
        [
            memory.interests.professional,
            memory.interests.personal_hobbies,
        ]
    )

    # Check context/facts
    has_context = any(
        [
            memory.context.key_facts,
            memory.important_facts,
        ]
    )

    # Check patterns/insights
    has_insights = any(
        [
            memory.insights.observed_patterns,
            memory.work_patterns.daily_rhythms,
        ]
    )

    return not any(
        [has_profile, has_technical, has_focus, has_interests, has_context, has_insights]
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
