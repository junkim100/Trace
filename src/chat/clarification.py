"""
Clarification System for Trace Chat

Handles ambiguous queries by detecting when clarification is needed
and managing the clarification flow with the user.

P7-07: Clarification system for agentic queries
"""

import logging
import uuid
from dataclasses import dataclass, field
from typing import Literal

from src.retrieval.time import parse_time_filter_with_ambiguity

logger = logging.getLogger(__name__)


@dataclass
class ClarificationOption:
    """A single option for clarification."""

    value: str  # The value to use if selected
    label: str  # Display label for the user
    description: str | None = None  # Optional additional context


@dataclass
class ClarificationRequest:
    """A request for clarification from the user."""

    query_id: str  # Unique ID for tracking this clarification
    original_query: str  # The original query that triggered clarification
    ambiguity_type: Literal["time", "entity", "scope"]
    question: str  # The clarification question to ask
    options: list[ClarificationOption]
    context: dict = field(default_factory=dict)  # Additional context for resolution

    def to_dict(self) -> dict:
        """Convert to dictionary representation."""
        return {
            "query_id": self.query_id,
            "original_query": self.original_query,
            "ambiguity_type": self.ambiguity_type,
            "question": self.question,
            "options": [
                {
                    "value": opt.value,
                    "label": opt.label,
                    "description": opt.description,
                }
                for opt in self.options
            ],
        }


@dataclass
class ClarificationResponse:
    """User's response to a clarification request."""

    query_id: str
    selected_value: str
    original_query: str


class ClarificationManager:
    """
    Manages the clarification flow for ambiguous queries.

    Responsibilities:
    1. Detect when clarification is needed (time ambiguity, entity ambiguity, etc.)
    2. Generate appropriate clarification questions
    3. Apply user's clarification choice to refine the query
    """

    def __init__(self):
        # Cache for pending clarifications (in production, use persistent storage)
        self._pending: dict[str, ClarificationRequest] = {}

    def check_for_clarification(self, query: str) -> ClarificationRequest | None:
        """
        Check if a query needs clarification.

        Examines the query for:
        - Ambiguous time references ("last July" without year)
        - Ambiguous entity references (multiple matches)
        - Ambiguous scope (unclear what data to search)

        Args:
            query: The user's query

        Returns:
            ClarificationRequest if clarification is needed, None otherwise
        """
        # Check for time ambiguity
        time_clarification = self._check_time_ambiguity(query)
        if time_clarification:
            return time_clarification

        # Future: Check for entity ambiguity
        # entity_clarification = self._check_entity_ambiguity(query)
        # if entity_clarification:
        #     return entity_clarification

        return None

    def _check_time_ambiguity(self, query: str) -> ClarificationRequest | None:
        """Check if the query has ambiguous time references."""
        result = parse_time_filter_with_ambiguity(query)

        if result is None:
            return None

        if not result.ambiguous:
            return None

        # Generate clarification request
        query_id = str(uuid.uuid4())

        options = [
            ClarificationOption(
                value=opt,
                label=opt,
                description=f"Search notes from {opt}",
            )
            for opt in result.clarification_options
        ]

        request = ClarificationRequest(
            query_id=query_id,
            original_query=query,
            ambiguity_type="time",
            question=f"Which time period did you mean by '{result.raw_expression}'?",
            options=options,
            context={
                "raw_expression": result.raw_expression,
                "default_filter": result.time_filter.to_dict() if result.time_filter else None,
            },
        )

        # Store for later resolution
        self._pending[query_id] = request

        return request

    def apply_clarification(self, response: ClarificationResponse) -> str:
        """
        Apply a clarification response to refine the original query.

        Args:
            response: The user's clarification response

        Returns:
            Refined query string with explicit time/entity reference
        """
        # Get the original request (if cached)
        original = self._pending.pop(response.query_id, None)

        if original is None:
            # Fallback: Just use the original query and selected value
            logger.warning(f"No cached clarification for {response.query_id}")
            return f"{response.original_query} ({response.selected_value})"

        # Refine the query based on ambiguity type
        if original.ambiguity_type == "time":
            return self._refine_time_query(
                original.original_query,
                original.context.get("raw_expression", ""),
                response.selected_value,
            )

        # Default: append the selection
        return f"{original.original_query} ({response.selected_value})"

    def _refine_time_query(self, query: str, raw_expression: str, selected_value: str) -> str:
        """
        Refine a query by replacing ambiguous time with explicit time.

        Args:
            query: Original query
            raw_expression: The ambiguous expression (e.g., "last july")
            selected_value: The selected clarification (e.g., "July 2025")

        Returns:
            Query with explicit time reference
        """
        import re

        # Replace the ambiguous expression with the explicit one
        # Handle various patterns
        patterns = [
            (rf"\blast\s+{re.escape(raw_expression.replace('last ', ''))}\b", selected_value),
            (rf"\b{re.escape(raw_expression)}\b", selected_value),
        ]

        refined = query
        for pattern, replacement in patterns:
            refined = re.sub(pattern, replacement, refined, flags=re.IGNORECASE)
            if refined != query:
                break

        # If no replacement happened, append the clarification
        if refined == query:
            refined = f"{query} (in {selected_value})"

        logger.info(f"Refined query: '{query}' -> '{refined}'")
        return refined

    def get_pending(self, query_id: str) -> ClarificationRequest | None:
        """Get a pending clarification request by ID."""
        return self._pending.get(query_id)

    def clear_pending(self, query_id: str) -> None:
        """Clear a pending clarification request."""
        self._pending.pop(query_id, None)


# Global instance
_clarification_manager: ClarificationManager | None = None


def get_clarification_manager() -> ClarificationManager:
    """Get the global clarification manager instance."""
    global _clarification_manager
    if _clarification_manager is None:
        _clarification_manager = ClarificationManager()
    return _clarification_manager


if __name__ == "__main__":
    import fire

    def check(query: str):
        """Check if a query needs clarification."""
        manager = ClarificationManager()
        result = manager.check_for_clarification(query)
        if result:
            return result.to_dict()
        return {"needs_clarification": False}

    def resolve(query: str, query_id: str, selected: str):
        """Resolve a clarification by applying user's choice."""
        manager = ClarificationManager()
        # First check to create the pending state
        manager.check_for_clarification(query)

        response = ClarificationResponse(
            query_id=query_id,
            selected_value=selected,
            original_query=query,
        )
        refined = manager.apply_clarification(response)
        return {"refined_query": refined}

    def demo():
        """Demo the clarification system."""
        manager = ClarificationManager()

        queries = [
            "What did I do last July?",  # Ambiguous
            "What did I do in July 2025?",  # Not ambiguous
            "What did I do yesterday?",  # Not ambiguous
            "last December activities",  # Ambiguous
        ]

        results = []
        for query in queries:
            result = manager.check_for_clarification(query)
            results.append(
                {
                    "query": query,
                    "needs_clarification": result is not None,
                    "clarification": result.to_dict() if result else None,
                }
            )

        return results

    fire.Fire({"check": check, "resolve": resolve, "demo": demo})
