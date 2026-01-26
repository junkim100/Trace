"""
Answer Synthesis Prompt for Trace

Generates grounded answers with citations based on retrieved notes
and context. Uses the LLM to synthesize coherent responses.

Includes user memory for personalized, engaging responses with follow-up questions.

P7-05: Answer synthesis prompt
"""

import logging
from dataclasses import dataclass
from datetime import datetime

from openai import OpenAI

from src.retrieval.aggregates import AggregateItem
from src.retrieval.graph import RelatedEntity
from src.retrieval.search import NoteMatch
from src.retrieval.time import TimeFilter

logger = logging.getLogger(__name__)

# Model for answer synthesis
ANSWER_MODEL = "gpt-5.2-2025-12-11"

# System prompt for answer synthesis with memory and follow-up questions
SYSTEM_PROMPT = """You are a helpful, personalized assistant that answers questions about a user's digital activity history. You have access to notes that summarize their activities, and you know things about the user from their memory profile.

Guidelines:
1. ALWAYS cite your sources using [Note: HH:00] format for hourly notes or [Note: YYYY-MM-DD] for daily notes
2. Only make claims that are supported by the provided notes
3. If the information isn't in the notes, say so honestly
4. When answering "most" or "top" questions, use the provided aggregates data
5. Keep answers concise but informative
6. Use natural language, not bullet points unless listing items
7. When relevant, mention the time context (e.g., "this morning", "last Tuesday")
8. If asked about something not in the notes, acknowledge the limitation
9. Use the user's name when appropriate to personalize the response
10. Be engaging and conversational, not robotic

IMPORTANT - Follow-up Questions:
After answering, suggest ONE thoughtful follow-up question to learn more about the user or continue the conversation. The follow-up should:
- Be relevant to what was discussed
- Help you learn something useful about the user (interests, preferences, work, etc.)
- Be optional and non-intrusive
- Be phrased conversationally

Format your response as:
1. Your answer to the question (with citations)
2. Then on a new line, a follow-up question starting with "💭 "

Example:
"You spent about 3 hours working on Python code in VS Code today [Note: 14:00]. Most of that time was focused on implementing the new API endpoint you mentioned.

💭 Are you building this for a personal project or is it work-related?"

Example citations:
- "You spent 3 hours coding in VS Code [Note: 14:00]."
- "On Monday, you focused primarily on Python development [Note: 2025-01-13]."
"""

# User prompt template with memory context
USER_PROMPT_TEMPLATE = """Question: {question}

Time context: {time_context}

## User Memory
{memory_context}

## Relevant Notes

{notes_context}

## Aggregates Data (if applicable)

{aggregates_context}

## Related Topics (if applicable)

{related_context}

---

Please answer the question based on the information above. Remember to cite your sources.
After your answer, include a thoughtful follow-up question starting with "💭 " to learn more about the user or continue the conversation."""


@dataclass
class AnswerContext:
    """Context for generating an answer."""

    question: str
    time_filter: TimeFilter | None
    notes: list[NoteMatch]
    aggregates: list[AggregateItem]
    related_entities: list[RelatedEntity]
    memory_context: str = ""  # User memory context for personalization

    def to_dict(self) -> dict:
        """Convert to dictionary representation."""
        return {
            "question": self.question,
            "time_filter": self.time_filter.to_dict() if self.time_filter else None,
            "notes_count": len(self.notes),
            "aggregates_count": len(self.aggregates),
            "related_entities_count": len(self.related_entities),
            "has_memory_context": bool(self.memory_context),
        }


@dataclass
class Citation:
    """A citation to a source note."""

    note_id: str
    note_type: str
    timestamp: datetime
    label: str  # Display label like "14:00" or "2025-01-13"

    def to_dict(self) -> dict:
        """Convert to dictionary representation."""
        return {
            "note_id": self.note_id,
            "note_type": self.note_type,
            "timestamp": self.timestamp.isoformat(),
            "label": self.label,
        }


@dataclass
class FollowUpQuestion:
    """A follow-up question to learn more about the user."""

    question: str
    context: str = ""  # What triggered this question
    category: str = ""  # What type of info it aims to learn (interest, preference, work, etc.)

    def to_dict(self) -> dict:
        return {
            "question": self.question,
            "context": self.context,
            "category": self.category,
        }


@dataclass
class SynthesizedAnswer:
    """A synthesized answer with citations and follow-up question."""

    answer: str
    citations: list[Citation]
    confidence: float
    model: str
    context_used: AnswerContext
    follow_up: FollowUpQuestion | None = None

    def to_dict(self) -> dict:
        """Convert to dictionary representation."""
        result = {
            "answer": self.answer,
            "citations": [c.to_dict() for c in self.citations],
            "confidence": self.confidence,
            "model": self.model,
            "context": self.context_used.to_dict(),
        }
        if self.follow_up:
            result["follow_up"] = self.follow_up.to_dict()
        return result


class AnswerPromptBuilder:
    """
    Builds prompts for answer synthesis.

    Handles:
    - Formatting notes context
    - Formatting aggregates data
    - Building citations
    - Token budget management
    """

    def __init__(
        self,
        max_notes: int = 10,
        max_aggregates: int = 10,
        max_related: int = 5,
    ):
        """
        Initialize the prompt builder.

        Args:
            max_notes: Maximum notes to include in context
            max_aggregates: Maximum aggregate items to include
            max_related: Maximum related entities to include
        """
        self.max_notes = max_notes
        self.max_aggregates = max_aggregates
        self.max_related = max_related

    def build_prompt(self, context: AnswerContext) -> tuple[str, str]:
        """
        Build the system and user prompts.

        Args:
            context: Answer context with question and evidence

        Returns:
            Tuple of (system_prompt, user_prompt)
        """
        # Build time context description
        time_context = self._build_time_context(context.time_filter)

        # Build notes context
        notes_context = self._build_notes_context(context.notes[: self.max_notes])

        # Build aggregates context
        aggregates_context = self._build_aggregates_context(
            context.aggregates[: self.max_aggregates]
        )

        # Build related entities context
        related_context = self._build_related_context(context.related_entities[: self.max_related])

        # Use memory context if provided
        memory_context = (
            context.memory_context if context.memory_context else "No user memory available yet."
        )

        # Format user prompt
        user_prompt = USER_PROMPT_TEMPLATE.format(
            question=context.question,
            time_context=time_context,
            memory_context=memory_context,
            notes_context=notes_context,
            aggregates_context=aggregates_context,
            related_context=related_context,
        )

        return SYSTEM_PROMPT, user_prompt

    def _build_time_context(self, time_filter: TimeFilter | None) -> str:
        """Build time context description."""
        if time_filter is None:
            return "All time (no specific time filter)"

        return f"{time_filter.description} ({time_filter.start.strftime('%Y-%m-%d %H:%M')} to {time_filter.end.strftime('%Y-%m-%d %H:%M')})"

    def _build_notes_context(self, notes: list[NoteMatch]) -> str:
        """Build notes context for the prompt."""
        if not notes:
            return "No relevant notes found."

        parts = []
        for note in notes:
            # Create citation label
            if note.note_type == "hour":
                label = note.start_ts.strftime("%H:00 on %Y-%m-%d")
            else:
                label = note.start_ts.strftime("%Y-%m-%d")

            # Build note summary
            note_text = f"### [Note: {label}]\n"
            note_text += f"Time: {note.start_ts.strftime('%Y-%m-%d %H:%M')} - {note.end_ts.strftime('%H:%M')}\n"

            if note.summary:
                note_text += f"Summary: {note.summary}\n"

            if note.categories:
                note_text += f"Categories: {', '.join(note.categories)}\n"

            if note.entities:
                entity_strs = []
                for entity in note.entities[:5]:  # Limit entities shown
                    entity_strs.append(f"{entity.get('name', '')} ({entity.get('type', '')})")
                if entity_strs:
                    note_text += f"Key entities: {', '.join(entity_strs)}\n"

            parts.append(note_text)

        return "\n".join(parts)

    def _build_aggregates_context(self, aggregates: list[AggregateItem]) -> str:
        """Build aggregates context for the prompt."""
        if not aggregates:
            return "No aggregate data available."

        parts = ["Time spent (in minutes):"]
        for item in aggregates:
            parts.append(f"- {item.key} ({item.key_type}): {item.value:.1f} minutes")

        return "\n".join(parts)

    def _build_related_context(self, related: list[RelatedEntity]) -> str:
        """Build related entities context."""
        if not related:
            return "No related topics found."

        parts = ["Related topics and entities:"]
        for entity in related:
            parts.append(
                f"- {entity.canonical_name} ({entity.entity_type}) "
                f"- {entity.edge_type} from {entity.source_entity_name}"
            )

        return "\n".join(parts)

    def extract_citations(self, notes: list[NoteMatch]) -> list[Citation]:
        """Extract citations from notes."""
        citations = []
        for note in notes:
            if note.note_type == "hour":
                label = note.start_ts.strftime("%H:00")
            else:
                label = note.start_ts.strftime("%Y-%m-%d")

            citations.append(
                Citation(
                    note_id=note.note_id,
                    note_type=note.note_type,
                    timestamp=note.start_ts,
                    label=label,
                )
            )
        return citations


def build_answer_prompt(
    question: str,
    notes: list[NoteMatch],
    time_filter: TimeFilter | None = None,
    aggregates: list[AggregateItem] | None = None,
    related_entities: list[RelatedEntity] | None = None,
    memory_context: str = "",
) -> tuple[str, str, AnswerContext]:
    """
    Build an answer prompt from context.

    Args:
        question: User's question
        notes: Relevant notes from search
        time_filter: Time range filter
        aggregates: Optional aggregate data
        related_entities: Optional related entities
        memory_context: Optional user memory context for personalization

    Returns:
        Tuple of (system_prompt, user_prompt, context)
    """
    context = AnswerContext(
        question=question,
        time_filter=time_filter,
        notes=notes,
        aggregates=aggregates or [],
        related_entities=related_entities or [],
        memory_context=memory_context,
    )

    builder = AnswerPromptBuilder()
    system_prompt, user_prompt = builder.build_prompt(context)

    return system_prompt, user_prompt, context


def extract_follow_up_question(answer_text: str) -> tuple[str, FollowUpQuestion | None]:
    """
    Extract follow-up question from the answer text.

    Args:
        answer_text: Raw answer from LLM

    Returns:
        Tuple of (clean_answer, follow_up_question)
    """
    import re

    # Look for follow-up question marker
    follow_up_pattern = r"💭\s*(.+?)(?:\n|$)"
    match = re.search(follow_up_pattern, answer_text)

    if match:
        follow_up_text = match.group(1).strip()
        # Remove the follow-up from the main answer
        clean_answer = re.sub(follow_up_pattern, "", answer_text).strip()

        # Determine category based on keywords
        category = "general"
        follow_up_lower = follow_up_text.lower()
        if any(word in follow_up_lower for word in ["work", "job", "project", "building"]):
            category = "work"
        elif any(word in follow_up_lower for word in ["hobby", "fun", "enjoy", "interest", "like"]):
            category = "interests"
        elif any(word in follow_up_lower for word in ["prefer", "rather", "better"]):
            category = "preferences"
        elif any(word in follow_up_lower for word in ["name", "call you"]):
            category = "profile"

        follow_up = FollowUpQuestion(
            question=follow_up_text,
            context="",
            category=category,
        )
        return clean_answer, follow_up

    return answer_text, None


class AnswerSynthesizer:
    """
    Synthesizes answers using LLM.

    Uses OpenAI API to generate grounded answers based on
    retrieved context.
    """

    def __init__(
        self,
        api_key: str | None = None,
        model: str = ANSWER_MODEL,
    ):
        """
        Initialize the answer synthesizer.

        Args:
            api_key: OpenAI API key
            model: Model to use for synthesis
        """
        self.model = model
        self._api_key = api_key
        self._client: OpenAI | None = None

    def _get_client(self) -> OpenAI:
        """Get or create the OpenAI client."""
        if self._client is None:
            self._client = OpenAI(api_key=self._api_key) if self._api_key else OpenAI()
        return self._client

    def synthesize(
        self,
        question: str,
        notes: list[NoteMatch],
        time_filter: TimeFilter | None = None,
        aggregates: list[AggregateItem] | None = None,
        related_entities: list[RelatedEntity] | None = None,
        include_memory: bool = True,
    ) -> SynthesizedAnswer:
        """
        Synthesize an answer to a question.

        Args:
            question: User's question
            notes: Relevant notes from search
            time_filter: Time range filter
            aggregates: Optional aggregate data
            related_entities: Optional related entities
            include_memory: Whether to include user memory context

        Returns:
            SynthesizedAnswer with the response, citations, and follow-up question
        """
        # Get user memory context if requested
        memory_context = ""
        if include_memory:
            try:
                from src.memory.memory import get_memory_context

                memory_context = get_memory_context()
            except Exception as e:
                logger.debug(f"Could not load memory context: {e}")

        # Build prompt
        system_prompt, user_prompt, context = build_answer_prompt(
            question=question,
            notes=notes,
            time_filter=time_filter,
            aggregates=aggregates,
            related_entities=related_entities,
            memory_context=memory_context,
        )

        # Call LLM
        try:
            client = self._get_client()
            response = client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.4,  # Slightly higher for more engaging responses
                max_completion_tokens=1200,  # Allow room for follow-up question
            )

            raw_answer = response.choices[0].message.content or ""

            # Extract follow-up question from the answer
            answer, follow_up = extract_follow_up_question(raw_answer)

            # Extract citations from the notes used
            builder = AnswerPromptBuilder()
            citations = builder.extract_citations(notes)

            # Calculate confidence based on note coverage
            confidence = min(1.0, len(notes) / 3)  # Higher confidence with more notes

            return SynthesizedAnswer(
                answer=answer,
                citations=citations,
                confidence=confidence,
                model=self.model,
                context_used=context,
                follow_up=follow_up,
            )

        except Exception as e:
            logger.error(f"Failed to synthesize answer: {e}")
            return SynthesizedAnswer(
                answer=f"I encountered an error while generating the answer: {e}",
                citations=[],
                confidence=0.0,
                model=self.model,
                context_used=context,
            )

    def synthesize_without_context(self, question: str) -> SynthesizedAnswer:
        """
        Generate a response when no context is available.

        Args:
            question: User's question

        Returns:
            SynthesizedAnswer indicating no data
        """
        context = AnswerContext(
            question=question,
            time_filter=None,
            notes=[],
            aggregates=[],
            related_entities=[],
        )

        answer = (
            "I don't have any relevant notes or activity data to answer this question. "
            "This could mean:\n"
            "1. No activity was captured during the time period you're asking about\n"
            "2. The topic you're asking about wasn't detected in your activities\n"
            "3. The time filter might be too restrictive\n\n"
            "Try broadening your time range or rephrasing your question."
        )

        return SynthesizedAnswer(
            answer=answer,
            citations=[],
            confidence=0.0,
            model=self.model,
            context_used=context,
        )


if __name__ == "__main__":
    import fire

    def demo():
        """Demo answer synthesis with mock data."""
        from datetime import timedelta

        # Create mock notes
        now = datetime.now()
        mock_notes = [
            NoteMatch(
                note_id="note-001",
                note_type="hour",
                start_ts=now - timedelta(hours=2),
                end_ts=now - timedelta(hours=1),
                file_path="/notes/2025/01/18/hour-20250118-14.md",
                summary="The user worked on Python code in VS Code, focusing on implementing a new API endpoint.",
                categories=["work", "coding"],
                entities=[
                    {"name": "Python", "type": "topic", "confidence": 0.9},
                    {"name": "VS Code", "type": "app", "confidence": 0.95},
                ],
                distance=0.2,
                score=0.8,
            ),
            NoteMatch(
                note_id="note-002",
                note_type="hour",
                start_ts=now - timedelta(hours=1),
                end_ts=now,
                file_path="/notes/2025/01/18/hour-20250118-15.md",
                summary="Continued Python development and reviewed documentation on GitHub.",
                categories=["work", "browsing"],
                entities=[
                    {"name": "Python", "type": "topic", "confidence": 0.85},
                    {"name": "GitHub", "type": "domain", "confidence": 0.8},
                ],
                distance=0.3,
                score=0.7,
            ),
        ]

        # Build prompt
        question = "What have I been working on today?"
        time_filter = TimeFilter(
            start=now - timedelta(hours=3),
            end=now,
            description="last 3 hours",
        )

        system_prompt, user_prompt, context = build_answer_prompt(
            question=question,
            notes=mock_notes,
            time_filter=time_filter,
        )

        print("=== System Prompt ===")
        print(system_prompt)
        print("\n=== User Prompt ===")
        print(user_prompt)

        return {"context": context.to_dict()}

    def synthesize(question: str):
        """Synthesize an answer (requires OpenAI API key)."""
        synthesizer = AnswerSynthesizer()
        result = synthesizer.synthesize_without_context(question)
        return result.to_dict()

    fire.Fire({"demo": demo, "synthesize": synthesize})
