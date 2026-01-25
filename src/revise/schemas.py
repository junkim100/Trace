"""
JSON Schema Validation for Daily Revision Output

Validates LLM output for daily revision against versioned schemas.
Supports retry on validation failure.

Part of P6-01: Daily revision prompt
"""

import json
import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, field_validator, model_validator

logger = logging.getLogger(__name__)

# Current schema version
DAILY_SCHEMA_VERSION = 1


class RevisedEntityItem(BaseModel):
    """An entity with revision information."""

    original_name: str = Field(..., description="Entity name as originally captured")
    canonical_name: str = Field(..., description="Normalized canonical name")
    type: str = Field(..., description="Entity type")
    confidence: float = Field(0.5, ge=0.0, le=1.0, description="Confidence score")


class HourlyRevisionItem(BaseModel):
    """Revision data for a single hourly note."""

    hour: str = Field(..., description="Hour in HH:00 format")
    note_id: str = Field(..., description="Original note ID")
    revised_summary: str = Field(..., description="Improved summary with day context")
    revised_entities: list[RevisedEntityItem] = Field(
        default_factory=list, description="Revised entities with canonical names"
    )
    additional_context: str | None = Field(None, description="New insights from day context")


class EntityNormalization(BaseModel):
    """Normalization mapping for entity variants."""

    original_names: list[str] = Field(..., description="List of variant names")
    canonical_name: str = Field(..., description="The canonical/normalized name")
    entity_type: str = Field(..., description="Entity type")
    confidence: float = Field(0.8, ge=0.0, le=1.0, description="Confidence in normalization")

    @field_validator("entity_type")
    @classmethod
    def validate_type(cls, v: str) -> str:
        valid_types = {
            "topic",
            "app",
            "domain",
            "document",
            "artist",
            "track",
            "video",
            "game",
            "person",
            "project",
        }
        if v.lower() not in valid_types:
            return "topic"  # Default to topic
        return v.lower()


class GraphEdgeItem(BaseModel):
    """A suggested graph edge between entities."""

    from_entity: str = Field(..., description="Source entity name")
    from_type: str = Field(..., description="Source entity type")
    to_entity: str = Field(..., description="Target entity name")
    to_type: str = Field(..., description="Target entity type")
    edge_type: str = Field(..., description="Type of relationship")
    weight: float = Field(0.5, ge=0.0, le=1.0, description="Edge weight")
    evidence: str | None = Field(None, description="Evidence for this relationship")

    @field_validator("edge_type")
    @classmethod
    def validate_edge_type(cls, v: str) -> str:
        valid_types = {
            "ABOUT_TOPIC",
            "WATCHED",
            "LISTENED_TO",
            "USED_APP",
            "VISITED_DOMAIN",
            "DOC_REFERENCE",
            "CO_OCCURRED_WITH",
            "STUDIED_WHILE",
        }
        v_upper = v.upper()
        if v_upper not in valid_types:
            return "CO_OCCURRED_WITH"  # Default
        return v_upper


class TopEntityItem(BaseModel):
    """A top entity with aggregated time."""

    name: str = Field(..., description="Entity name")
    total_minutes: int = Field(0, ge=0, description="Total minutes")
    type: str | None = Field(None, description="Entity type (for media)")


class TopEntitiesSection(BaseModel):
    """Top entities by category."""

    topics: list[TopEntityItem] = Field(default_factory=list)
    apps: list[TopEntityItem] = Field(default_factory=list)
    domains: list[TopEntityItem] = Field(default_factory=list)
    media: list[TopEntityItem] = Field(default_factory=list)


class DailyRevisionSchema(BaseModel):
    """
    Complete schema for daily revision output.

    This is the canonical schema that all daily revision LLM outputs must conform to.
    """

    schema_version: int = Field(DAILY_SCHEMA_VERSION, description="Schema version number")
    day_summary: str = Field(..., description="3-5 sentence overview of the day")
    primary_focus: str | None = Field(None, description="Main theme or activity type")
    accomplishments: list[str] = Field(default_factory=list, description="Key accomplishments")
    hourly_revisions: list[HourlyRevisionItem] = Field(
        default_factory=list, description="Revisions for each hourly note"
    )
    entity_normalizations: list[EntityNormalization] = Field(
        default_factory=list, description="Entity normalization mappings"
    )
    graph_edges: list[GraphEdgeItem] = Field(
        default_factory=list, description="Suggested graph edges"
    )
    top_entities: TopEntitiesSection = Field(
        default_factory=TopEntitiesSection, description="Top entities by time"
    )
    patterns: list[str] = Field(default_factory=list, description="Observed patterns")
    location_summary: str | None = Field(None, description="Location summary")

    @model_validator(mode="before")
    @classmethod
    def handle_missing_fields(cls, data: dict[str, Any]) -> dict[str, Any]:
        """Handle missing or null fields gracefully."""
        if isinstance(data, dict):
            # Ensure schema_version
            if "schema_version" not in data:
                data["schema_version"] = DAILY_SCHEMA_VERSION

            # Ensure required string field
            if "day_summary" not in data or not data["day_summary"]:
                data["day_summary"] = "No summary available for this day."

            # Ensure top_entities section exists
            if "top_entities" not in data or data["top_entities"] is None:
                data["top_entities"] = {
                    "topics": [],
                    "apps": [],
                    "domains": [],
                    "media": [],
                }
            elif isinstance(data["top_entities"], dict):
                for key in ["topics", "apps", "domains", "media"]:
                    if key not in data["top_entities"]:
                        data["top_entities"][key] = []

            # Convert null lists to empty lists
            list_fields = [
                "accomplishments",
                "hourly_revisions",
                "entity_normalizations",
                "graph_edges",
                "patterns",
            ]
            for field in list_fields:
                if field not in data or data[field] is None:
                    data[field] = []

        return data


@dataclass
class DailyValidationResult:
    """Result of daily schema validation."""

    valid: bool
    data: DailyRevisionSchema | None = None
    error: str | None = None
    raw_json: dict | None = None


def validate_daily_revision(
    json_str: str | dict,
    strict: bool = False,
) -> DailyValidationResult:
    """
    Validate a daily revision output against the schema.

    Args:
        json_str: JSON string or dict to validate
        strict: If True, fail on any non-conforming data

    Returns:
        DailyValidationResult with parsed data or error
    """
    # Parse JSON if string
    if isinstance(json_str, str):
        try:
            data = json.loads(json_str)
        except json.JSONDecodeError as e:
            return DailyValidationResult(
                valid=False,
                error=f"Invalid JSON: {e}",
                raw_json=None,
            )
    else:
        data = json_str

    # Validate against schema
    try:
        validated = DailyRevisionSchema.model_validate(data)

        return DailyValidationResult(
            valid=True,
            data=validated,
            error=None,
            raw_json=data,
        )

    except Exception as e:
        return DailyValidationResult(
            valid=False,
            error=str(e),
            raw_json=data,
        )


def fix_common_issues(json_str: str) -> str:
    """
    Attempt to fix common JSON issues from LLM output.

    Args:
        json_str: Potentially malformed JSON string

    Returns:
        Fixed JSON string
    """
    # Remove markdown code blocks
    if "```json" in json_str:
        json_str = json_str.split("```json")[-1]
    if "```" in json_str:
        json_str = json_str.split("```")[0]

    # Strip whitespace
    json_str = json_str.strip()

    # Try to find JSON object boundaries
    if not json_str.startswith("{"):
        start_idx = json_str.find("{")
        if start_idx != -1:
            json_str = json_str[start_idx:]

    if not json_str.endswith("}"):
        end_idx = json_str.rfind("}")
        if end_idx != -1:
            json_str = json_str[: end_idx + 1]

    return json_str


def validate_with_retry(
    json_str: str,
    max_attempts: int = 2,
) -> DailyValidationResult:
    """
    Validate JSON with automatic fix attempts.

    Args:
        json_str: JSON string to validate
        max_attempts: Maximum validation attempts

    Returns:
        DailyValidationResult from best attempt
    """
    attempt = 0
    last_result = None

    while attempt < max_attempts:
        attempt += 1

        # Fix common issues
        if attempt > 1:
            json_str = fix_common_issues(json_str)

        result = validate_daily_revision(json_str)

        if result.valid:
            return result

        last_result = result
        logger.debug(f"Daily validation attempt {attempt} failed: {result.error}")

    return last_result or DailyValidationResult(valid=False, error="Validation failed")


def generate_empty_daily_revision(
    day: datetime,
    reason: str = "No hourly notes found",
) -> DailyRevisionSchema:
    """
    Generate an empty/minimal daily revision when no data is available.

    Args:
        day: The day being revised
        reason: Reason for empty revision

    Returns:
        Minimal valid DailyRevisionSchema
    """
    return DailyRevisionSchema(
        schema_version=DAILY_SCHEMA_VERSION,
        day_summary=f"{reason} for {day.strftime('%A, %B %d, %Y')}.",
        primary_focus=None,
        accomplishments=[],
        hourly_revisions=[],
        entity_normalizations=[],
        graph_edges=[],
        top_entities=TopEntitiesSection(),
        patterns=[],
        location_summary=None,
    )


if __name__ == "__main__":
    import fire

    def validate(json_file: str | None = None, json_str: str | None = None):
        """
        Validate a JSON file or string against the daily revision schema.

        Args:
            json_file: Path to JSON file
            json_str: JSON string to validate
        """
        if json_file:
            with open(json_file) as f:
                content = f.read()
        elif json_str:
            content = json_str
        else:
            # Demo with sample data
            content = json.dumps(
                {
                    "day_summary": "A productive day focused on Python development.",
                    "primary_focus": "coding",
                    "accomplishments": ["Completed feature X", "Fixed bug Y"],
                    "hourly_revisions": [
                        {
                            "hour": "10:00",
                            "note_id": "note-001",
                            "revised_summary": "Deep work on Python project.",
                            "revised_entities": [
                                {
                                    "original_name": "VS Code",
                                    "canonical_name": "visual studio code",
                                    "type": "app",
                                    "confidence": 0.95,
                                }
                            ],
                            "additional_context": "Part of morning coding session.",
                        }
                    ],
                    "entity_normalizations": [
                        {
                            "original_names": ["VS Code", "VSCode", "Visual Studio Code"],
                            "canonical_name": "visual studio code",
                            "entity_type": "app",
                            "confidence": 0.95,
                        }
                    ],
                    "graph_edges": [
                        {
                            "from_entity": "Python",
                            "from_type": "topic",
                            "to_entity": "visual studio code",
                            "to_type": "app",
                            "edge_type": "USED_APP",
                            "weight": 0.9,
                            "evidence": "Wrote Python code in VS Code",
                        }
                    ],
                    "top_entities": {
                        "topics": [{"name": "Python", "total_minutes": 180}],
                        "apps": [{"name": "visual studio code", "total_minutes": 240}],
                        "domains": [{"name": "github.com", "total_minutes": 45}],
                        "media": [],
                    },
                    "patterns": ["Morning deep work sessions are most productive"],
                    "location_summary": "Home office all day",
                }
            )

        result = validate_with_retry(content)

        return {
            "valid": result.valid,
            "error": result.error,
            "schema_version": result.data.schema_version if result.data else None,
            "day_summary": result.data.day_summary if result.data else None,
            "hourly_revisions_count": len(result.data.hourly_revisions) if result.data else 0,
            "normalizations_count": len(result.data.entity_normalizations) if result.data else 0,
            "edges_count": len(result.data.graph_edges) if result.data else 0,
        }

    def schema():
        """Show the Pydantic schema as JSON Schema."""
        print(json.dumps(DailyRevisionSchema.model_json_schema(), indent=2))

    fire.Fire({"validate": validate, "schema": schema})
