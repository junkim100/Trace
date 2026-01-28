"""
Answer Synthesis Prompt for Trace

Generates grounded answers with citations based on retrieved notes
and context. Uses the LLM to synthesize coherent responses.

Includes user memory for personalized, engaging responses with follow-up questions.

v0.8.0: Added unified citation model for both note and web sources with
inline citation support ([1], [2], etc.) and Perplexity-style rendering.

P7-05: Answer synthesis prompt
"""

import logging
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any

from openai import OpenAI

from src.retrieval.aggregates import AggregateItem
from src.retrieval.graph import RelatedEntity
from src.retrieval.search import NoteMatch
from src.retrieval.time import TimeFilter

logger = logging.getLogger(__name__)


# ============================================================================
# Unified Citation Model (v0.8.0)
# ============================================================================


class CitationType(str, Enum):
    """Type of citation source."""

    NOTE = "note"
    WEB = "web"


@dataclass
class UnifiedCitation:
    """
    Unified citation model for both note and web sources.

    This enables Perplexity-style inline citations [1], [2] that can
    reference either user activity notes or web search results.
    """

    id: str  # Citation number (e.g., "1", "2")
    type: CitationType
    label: str  # Display label

    # Note-specific fields
    note_id: str | None = None
    note_type: str | None = None  # "hourly" or "daily"
    timestamp: str | None = None
    note_content: str | None = None  # Snippet for popup preview

    # Web-specific fields
    url: str | None = None
    title: str | None = None
    snippet: str | None = None
    accessed_at: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary representation."""
        result: dict[str, Any] = {
            "id": self.id,
            "type": self.type.value,
            "label": self.label,
        }

        if self.type == CitationType.NOTE:
            result.update(
                {
                    "note_id": self.note_id,
                    "note_type": self.note_type,
                    "timestamp": self.timestamp,
                    "note_content": self.note_content,
                }
            )
        else:  # WEB
            result.update(
                {
                    "url": self.url,
                    "title": self.title,
                    "snippet": self.snippet,
                    "accessed_at": self.accessed_at,
                }
            )

        return result


class CitationBuilder:
    """
    Builds unified citations from notes and web results.

    Tracks citations to avoid duplicates and assigns sequential IDs.
    """

    def __init__(self) -> None:
        self._citations: list[UnifiedCitation] = []
        self._note_map: dict[str, str] = {}  # note_id -> citation_id
        self._web_map: dict[str, str] = {}  # url -> citation_id
        self._next_id = 1

    def add_note(self, note: NoteMatch) -> str:
        """
        Add a note citation, return citation ID.

        Args:
            note: NoteMatch object from search results

        Returns:
            Citation ID (e.g., "1")
        """
        if note.note_id in self._note_map:
            return self._note_map[note.note_id]

        cit_id = str(self._next_id)
        self._next_id += 1

        # Extract snippet for popup (first 300 chars of summary)
        content_snippet = ""
        if note.summary:
            content_snippet = (
                note.summary[:300] + "..." if len(note.summary) > 300 else note.summary
            )

        # Create label based on note type
        if note.note_type == "hour":
            label = note.start_ts.strftime("%b %d %H:%M")
        else:
            label = note.start_ts.strftime("%b %d, %Y")

        citation = UnifiedCitation(
            id=cit_id,
            type=CitationType.NOTE,
            label=label,
            note_id=note.note_id,
            note_type=note.note_type,
            timestamp=note.start_ts.isoformat(),
            note_content=content_snippet,
        )

        self._citations.append(citation)
        self._note_map[note.note_id] = cit_id
        return cit_id

    def add_web(self, title: str, url: str, snippet: str) -> str:
        """
        Add a web citation, return citation ID.

        Args:
            title: Page title
            url: Page URL
            snippet: Content snippet

        Returns:
            Citation ID (e.g., "2")
        """
        if url in self._web_map:
            return self._web_map[url]

        cit_id = str(self._next_id)
        self._next_id += 1

        # Truncate title for label
        label = title[:40] + "..." if len(title) > 40 else title

        citation = UnifiedCitation(
            id=cit_id,
            type=CitationType.WEB,
            label=label,
            url=url,
            title=title,
            snippet=snippet[:200] if snippet else "",
            accessed_at=datetime.now().isoformat(),
        )

        self._citations.append(citation)
        self._web_map[url] = cit_id
        return cit_id

    def get_citations(self) -> list[UnifiedCitation]:
        """Get all citations in order."""
        return self._citations

    def get_note_id_for_citation(self, citation_id: str) -> str | None:
        """Get the note_id for a given citation ID."""
        for citation in self._citations:
            if citation.id == citation_id and citation.type == CitationType.NOTE:
                return citation.note_id
        return None

    def build_context_for_llm(
        self, notes: list[NoteMatch], web_results: list[dict[str, Any]] | None = None
    ) -> tuple[str, str]:
        """
        Build context strings with citation markers for the LLM.

        Returns:
            Tuple of (notes_context, web_context) with [N] markers
        """
        notes_parts = []
        for note in notes:
            cit_id = self.add_note(note)
            label = f"[{cit_id}]"

            note_text = f"### Source {label}\n"
            note_text += f"Time: {note.start_ts.strftime('%Y-%m-%d %H:%M')}\n"
            if note.summary:
                note_text += f"Summary: {note.summary}\n"
            if note.categories:
                note_text += f"Categories: {', '.join(note.categories)}\n"

            notes_parts.append(note_text)

        web_parts = []
        if web_results:
            for result in web_results:
                title = result.get("title", "")
                url = result.get("url", "")
                snippet = result.get("snippet", "")

                if url:
                    cit_id = self.add_web(title, url, snippet)
                    label = f"[{cit_id}]"

                    web_text = f"### Source {label}\n"
                    web_text += f"Title: {title}\n"
                    web_text += f"URL: {url}\n"
                    if snippet:
                        web_text += f"Content: {snippet}\n"

                    web_parts.append(web_text)

        notes_context = "\n".join(notes_parts) if notes_parts else "No activity notes found."
        web_context = "\n".join(web_parts) if web_parts else "No web search results."

        return notes_context, web_context


# Model for answer synthesis
ANSWER_MODEL = "gpt-5.2-2025-12-11"

# System prompt for answer synthesis with memory and follow-up questions
SYSTEM_PROMPT = """You are a helpful, personalized assistant that answers questions about a user's digital activity history. You have access to notes that summarize their activities, and you know things about the user from their memory profile.

## CRITICAL: Detecting False Positives in Notes

The activity notes are generated by an AI analyzing screenshots, which can sometimes misinterpret what it sees. Be skeptical of the following and DO NOT report them as actual user activity:

### Desktop Wallpaper Confusion
- Notes mentioning "admiring", "viewing", or "contemplating" city skylines, landscapes, or artistic imagery
- System Settings → Wallpaper/Desktop mentioned without other meaningful context
- Any "activity" that sounds like appreciating static imagery rather than actual work
- **These are likely misinterpretations of the user's DESKTOP WALLPAPER**

### Questions to Ask Yourself
- "Would this person really spend time admiring their wallpaper?"
- "Does this activity make sense given the context of their other activities?"
- "Is this describing a background element rather than active work?"

### How to Handle Suspected Misattributions
- OMIT wallpaper-related "activities" from your answer entirely
- If the ONLY activity in a time period is wallpaper-related, say "You were idle" or "No significant activity"
- Focus on activities involving actual applications, documents, websites, or communication
- **NEVER include your reasoning about what you filtered out** - just silently omit it

## Guidelines

1. Only make claims that are supported by the provided notes
2. If the information isn't in the notes, say so honestly
3. When answering "most" or "top" questions, use the provided aggregates data
4. Keep answers concise but informative
5. Use natural language, not bullet points unless listing items
6. When relevant, mention the time context naturally (e.g., "this morning", "around 2pm", "last Tuesday")
7. If asked about something not in the notes, acknowledge the limitation
8. Use the user's name when appropriate to personalize the response
9. Be engaging and conversational, not robotic
10. Do NOT use bracket notation like [Note: HH:00] - just refer to times naturally in your response
11. FILTER OUT any wallpaper/background misattributions before including them in your answer
12. NEVER include internal reasoning, exclusion notes, or meta-commentary like "(Excluded: ...)" or "(Note: ...)" in your response - just answer directly

{follow_up_instructions}
"""

# Follow-up instructions only when memory is sparse
FOLLOW_UP_INSTRUCTIONS_SPARSE = """IMPORTANT - Follow-up Questions:
Since we don't know much about the user yet, after answering, suggest ONE thoughtful follow-up question to learn more about them. The follow-up should:
- Be relevant to what was discussed
- Help you learn something useful about the user (interests, preferences, work, etc.)
- Be optional and non-intrusive
- Be phrased conversationally

Format your response as:
1. Your answer to the question
2. Then on a new line, a follow-up question starting with "💭 "

Example:
"You spent about 3 hours working on Python code in VS Code today.

💭 Are you building this for a personal project or is it work-related?"
"""

# No follow-up when we already know the user well
FOLLOW_UP_INSTRUCTIONS_NONE = (
    """Do NOT include any follow-up questions. Just answer the question directly and concisely."""
)

# ============================================================================
# Web-Augmented Answer Prompts (v0.8.0)
# ============================================================================

# System prompt for web-augmented answers with inline citations
WEB_AUGMENTED_SYSTEM_PROMPT = """You are a helpful assistant that answers questions about a user's digital activity history, augmented with relevant web search results when appropriate.

You have access to:
1. User activity notes from their personal Trace app
2. Web search results that provide additional context

## Citation Rules (CRITICAL)

Use inline citations in brackets: [1], [2], etc. to reference your sources:
- Use note citations [N] when referencing the user's past activities
- Use web citations [N] when providing external context, timelines, or current information
- Citations should flow naturally within sentences

Example: "You worked on the React project last Tuesday [1]. React 19 was released around that time with new features like server components [2], which may explain the documentation you were reading [3]."

## Priority Rules

1. **User's activity data is primary** - The main focus should be on what the user actually did
2. **Web results augment, not replace** - Use web search to provide context, not to answer instead
3. **Be honest about sources** - If info comes from web search vs. notes, make it clear through citations
4. **If information conflicts** - Prefer user's notes for what they did, web for factual context

## Guidelines

- Keep answers concise but informative
- Use natural language with citations integrated smoothly
- Filter out any wallpaper/background misattributions from notes
- Do NOT repeat the same citation multiple times in a row
- Only cite sources that you actually reference
- NEVER include internal reasoning, exclusion notes, or meta-commentary like "(Excluded: ...)" in your response

{follow_up_instructions}
"""

# User prompt template for web-augmented answers
WEB_AUGMENTED_USER_PROMPT = """Question: {question}

Time context: {time_context}

## User Memory
{memory_context}

## User's Activity Notes
{notes_context}

## Web Search Results
{web_context}

## Aggregates Data (if applicable)
{aggregates_context}

---

Answer the question using the information above. Remember to use inline citations [N] naturally in your response."""

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

Please answer the question based on the information above. Remember to cite your sources."""


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

        # Determine if we should include follow-up instructions
        # Only include if memory is sparse (no name, no occupation, few interests)
        follow_up_instructions = self._determine_follow_up_instructions(context.memory_context)

        # Format system prompt with appropriate follow-up instructions
        system_prompt = SYSTEM_PROMPT.format(follow_up_instructions=follow_up_instructions)

        # Format user prompt
        user_prompt = USER_PROMPT_TEMPLATE.format(
            question=context.question,
            time_context=time_context,
            memory_context=memory_context,
            notes_context=notes_context,
            aggregates_context=aggregates_context,
            related_context=related_context,
        )

        return system_prompt, user_prompt

    def _determine_follow_up_instructions(self, memory_context: str) -> str:
        """
        Determine whether to include follow-up question instructions.

        Only asks follow-up questions when memory is sparse (missing key info).

        Args:
            memory_context: The user's memory context string

        Returns:
            Follow-up instructions string (or empty to skip follow-ups)
        """
        if not memory_context or memory_context == "No user memory available yet.":
            return FOLLOW_UP_INSTRUCTIONS_SPARSE

        # Check for key indicators of a populated memory
        memory_lower = memory_context.lower()

        # If we have a name and at least some other info, skip follow-ups
        has_name = "name:" in memory_lower and "not set" not in memory_lower
        has_role = "role:" in memory_lower or "occupation:" in memory_lower
        has_interests = "interests:" in memory_lower or "hobbies:" in memory_lower

        # Memory is considered "populated" if we have name + at least one other field
        if has_name and (has_role or has_interests):
            return FOLLOW_UP_INSTRUCTIONS_NONE

        # Memory is sparse - include follow-up questions
        return FOLLOW_UP_INSTRUCTIONS_SPARSE

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

    def synthesize_with_web(
        self,
        question: str,
        notes: list[NoteMatch],
        web_results: list[dict[str, Any]],
        time_filter: TimeFilter | None = None,
        aggregates: list[AggregateItem] | None = None,
        include_memory: bool = True,
    ) -> tuple[str, list[UnifiedCitation]]:
        """
        Synthesize an answer using both notes and web search results.

        This uses the web-augmented prompt with inline citations [1], [2], etc.

        Args:
            question: User's question
            notes: Relevant notes from search
            web_results: Web search results (list of dicts with title, url, snippet)
            time_filter: Time range filter
            aggregates: Optional aggregate data
            include_memory: Whether to include user memory context

        Returns:
            Tuple of (answer_text, unified_citations)
        """
        # Get user memory context if requested
        memory_context = ""
        if include_memory:
            try:
                from src.memory.memory import get_memory_context

                memory_context = get_memory_context()
            except Exception as e:
                logger.debug(f"Could not load memory context: {e}")

        # Build time context description
        if time_filter:
            time_context = (
                f"{time_filter.description} "
                f"({time_filter.start.strftime('%Y-%m-%d %H:%M')} to "
                f"{time_filter.end.strftime('%Y-%m-%d %H:%M')})"
            )
        else:
            time_context = "All time (no specific time filter)"

        # Build aggregates context
        if aggregates:
            agg_parts = ["Time spent (in minutes):"]
            for item in aggregates[:10]:
                agg_parts.append(f"- {item.key} ({item.key_type}): {item.value:.1f} minutes")
            aggregates_context = "\n".join(agg_parts)
        else:
            aggregates_context = "No aggregate data available."

        # Use CitationBuilder to build context with [N] markers
        citation_builder = CitationBuilder()
        notes_context, web_context = citation_builder.build_context_for_llm(notes, web_results)

        # Determine follow-up instructions
        if not memory_context or memory_context == "No user memory available yet.":
            follow_up_instructions = FOLLOW_UP_INSTRUCTIONS_SPARSE
        else:
            follow_up_instructions = FOLLOW_UP_INSTRUCTIONS_NONE

        # Build prompts
        system_prompt = WEB_AUGMENTED_SYSTEM_PROMPT.format(
            follow_up_instructions=follow_up_instructions
        )
        user_prompt = WEB_AUGMENTED_USER_PROMPT.format(
            question=question,
            time_context=time_context,
            memory_context=memory_context or "No user memory available yet.",
            notes_context=notes_context,
            web_context=web_context,
            aggregates_context=aggregates_context,
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
                temperature=0.4,
                max_completion_tokens=1500,  # More room for citations
            )

            raw_answer = response.choices[0].message.content or ""

            # Extract follow-up question if present
            answer, _ = extract_follow_up_question(raw_answer)

            # Get the unified citations
            unified_citations = citation_builder.get_citations()

            return answer, unified_citations

        except Exception as e:
            logger.error(f"Failed to synthesize web-augmented answer: {e}")
            return (
                f"I encountered an error while generating the answer: {e}",
                citation_builder.get_citations(),
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
