"""
Conversation Context Builder for Trace Chat

Manages the context window for LLM calls with conversation history.
Implements token budgeting and automatic summarization of older messages.
"""

import logging
from dataclasses import dataclass

from openai import OpenAI

from src.chat.conversations import ConversationManager, Message, get_conversation_manager
from src.core.config import get_api_key

logger = logging.getLogger(__name__)

# Model for summarization (fast and cheap)
SUMMARY_MODEL = "gpt-4o-mini"

# Model for title generation
TITLE_MODEL = "gpt-4o-mini"


@dataclass
class BuiltContext:
    """Result of building conversation context."""

    context_text: str  # Formatted context for LLM prompt
    message_count: int  # Number of messages included
    has_summary: bool  # Whether a summary was prepended
    total_tokens_estimate: int  # Rough token estimate


class ConversationContextBuilder:
    """
    Builds optimized context for LLM calls with conversation history.

    Strategy:
    1. Always include last N messages verbatim (most recent/relevant)
    2. If history > threshold, summarize older messages
    3. Summary cached in conversation_context table for reuse

    Token Budget (~4000 tokens for conversation):
    - Recent messages (last 10): ~2500 tokens
    - Summary of older msgs: ~1500 tokens
    """

    MAX_RECENT_MESSAGES = 10  # Always include last N messages
    MAX_CONTEXT_TOKENS = 4000  # Token budget for conversation context
    SUMMARY_TRIGGER = 15  # Summarize when history exceeds this
    CHARS_PER_TOKEN = 4  # Rough estimate for token counting

    def __init__(
        self,
        manager: ConversationManager | None = None,
        api_key: str | None = None,
    ):
        """Initialize the context builder.

        Args:
            manager: ConversationManager instance
            api_key: OpenAI API key for summarization
        """
        self.manager = manager or get_conversation_manager()
        self._api_key = api_key

    def _get_api_key(self) -> str | None:
        """Get API key, checking config if not set."""
        if self._api_key:
            return self._api_key
        return get_api_key()

    def build_context(self, conversation_id: str) -> BuiltContext:
        """Build conversation context for LLM prompt.

        Args:
            conversation_id: The conversation to build context for

        Returns:
            BuiltContext with formatted text and metadata
        """
        # Get recent messages
        recent_messages = self.manager.get_recent_messages(
            conversation_id,
            max_messages=self.MAX_RECENT_MESSAGES,
        )

        if not recent_messages:
            return BuiltContext(
                context_text="",
                message_count=0,
                has_summary=False,
                total_tokens_estimate=0,
            )

        # Check if we need to include a summary
        total_count = self.manager.get_message_count(conversation_id)
        has_summary = False
        summary_text = ""

        if total_count > self.SUMMARY_TRIGGER:
            # Get cached summary
            context = self.manager.get_context(conversation_id)
            if context and context.summary_text:
                summary_text = context.summary_text
                has_summary = True

        # Format context
        context_parts = []

        if summary_text:
            context_parts.append(f"[Earlier in this conversation: {summary_text}]")
            context_parts.append("")

        for msg in recent_messages:
            role_label = "User" if msg.role == "user" else "Assistant"
            context_parts.append(f"{role_label}: {msg.content}")

        context_text = "\n".join(context_parts)

        # Estimate tokens
        token_estimate = len(context_text) // self.CHARS_PER_TOKEN

        return BuiltContext(
            context_text=context_text,
            message_count=len(recent_messages),
            has_summary=has_summary,
            total_tokens_estimate=token_estimate,
        )

    def maybe_update_summary(self, conversation_id: str) -> bool:
        """Generate or update summary if needed.

        Should be called after adding messages to a conversation.
        Runs summarization only when message count exceeds threshold
        and there are messages not yet summarized.

        Args:
            conversation_id: The conversation to potentially summarize

        Returns:
            True if summary was updated, False otherwise
        """
        total_count = self.manager.get_message_count(conversation_id)

        if total_count <= self.SUMMARY_TRIGGER:
            return False

        # Get existing context
        context = self.manager.get_context(conversation_id)

        # Calculate how many messages to summarize
        # We want to summarize all except the last MAX_RECENT_MESSAGES
        messages_to_summarize = total_count - self.MAX_RECENT_MESSAGES

        if messages_to_summarize <= 0:
            return False

        # Check if we already have a recent enough summary
        if context and context.summary_text:
            # Could add logic here to skip if summary is recent
            # For now, regenerate when we hit the threshold
            pass

        # Get messages to summarize (all except recent)
        all_messages = self.manager.get_messages(
            conversation_id,
            limit=messages_to_summarize,
            order="asc",
        )

        if not all_messages:
            return False

        # Generate summary
        summary = self._generate_summary(all_messages)

        if summary:
            # Estimate token count
            token_count = len(summary) // self.CHARS_PER_TOKEN
            self.manager.update_context(conversation_id, summary, token_count)
            return True

        return False

    def _generate_summary(self, messages: list[Message]) -> str | None:
        """Generate a summary of messages using LLM.

        Args:
            messages: Messages to summarize

        Returns:
            Summary text or None if failed
        """
        api_key = self._get_api_key()
        if not api_key:
            logger.warning("No API key available for summarization")
            return None

        # Format messages for summarization
        transcript = []
        for msg in messages:
            role_label = "User" if msg.role == "user" else "Assistant"
            # Truncate very long messages
            content = msg.content[:500] + "..." if len(msg.content) > 500 else msg.content
            transcript.append(f"{role_label}: {content}")

        transcript_text = "\n".join(transcript)

        prompt = f"""Summarize this conversation excerpt for context. Focus on:
- Key questions the user asked
- Important facts or answers discovered
- Ongoing topics or threads

Keep the summary concise (under 300 words). Write in past tense.

Conversation:
{transcript_text}

Summary:"""

        try:
            client = OpenAI(api_key=api_key)
            response = client.chat.completions.create(
                model=SUMMARY_MODEL,
                messages=[
                    {
                        "role": "system",
                        "content": "You summarize conversation excerpts concisely for context.",
                    },
                    {"role": "user", "content": prompt},
                ],
                temperature=0.3,
                max_tokens=400,
            )

            return response.choices[0].message.content

        except Exception as e:
            logger.error(f"Failed to generate summary: {e}")
            return None


def generate_conversation_title(
    first_query: str,
    first_response: str,
    api_key: str | None = None,
) -> str:
    """Generate a title for a conversation from the first exchange.

    Args:
        first_query: The user's first message
        first_response: The assistant's first response
        api_key: OpenAI API key

    Returns:
        Generated title (3-6 words)
    """
    api_key = api_key or get_api_key()
    if not api_key:
        # Fallback to truncated query
        words = first_query.split()[:5]
        return " ".join(words) + ("..." if len(first_query.split()) > 5 else "")

    # Truncate for prompt
    query_preview = first_query[:200]
    response_preview = first_response[:300]

    prompt = f"""Generate a short, descriptive title (3-6 words) for this conversation:

User: {query_preview}
Assistant: {response_preview}

The title should capture the main topic or question. Be specific but concise.
Examples of good titles:
- "Weekly app usage analysis"
- "Python debugging session"
- "Music listening patterns"
- "Project planning discussion"

Title:"""

    try:
        client = OpenAI(api_key=api_key)
        response = client.chat.completions.create(
            model=TITLE_MODEL,
            messages=[
                {
                    "role": "system",
                    "content": "Generate concise conversation titles (3-6 words).",
                },
                {"role": "user", "content": prompt},
            ],
            temperature=0.5,
            max_tokens=20,
        )

        title = response.choices[0].message.content or ""
        # Clean up the title
        title = title.strip().strip('"').strip("'")
        # Ensure reasonable length
        if len(title) > 60:
            title = title[:57] + "..."

        return title or "New Conversation"

    except Exception as e:
        logger.error(f"Failed to generate title: {e}")
        # Fallback to truncated query
        words = first_query.split()[:5]
        return " ".join(words) + ("..." if len(first_query.split()) > 5 else "")
