"""IPC handlers for conversation management.

This module provides handlers for creating, listing, updating, and deleting
conversations, as well as sending messages within conversations.
"""

import logging
from datetime import datetime
from typing import Any

from src.chat.api import ChatAPI, ChatRequest
from src.chat.context import (
    ConversationContextBuilder,
    generate_conversation_title,
)
from src.chat.conversations import get_conversation_manager
from src.core.config import get_api_key
from src.trace_app.ipc.server import handler

logger = logging.getLogger(__name__)

# Singleton instances
_chat_api: ChatAPI | None = None
_context_builder: ConversationContextBuilder | None = None


def _get_chat_api() -> ChatAPI:
    """Get or create the ChatAPI instance."""
    global _chat_api
    if _chat_api is None:
        api_key = get_api_key()
        _chat_api = ChatAPI(api_key=api_key)
    return _chat_api


def _get_context_builder() -> ConversationContextBuilder:
    """Get or create the ConversationContextBuilder instance."""
    global _context_builder
    if _context_builder is None:
        _context_builder = ConversationContextBuilder()
    return _context_builder


@handler("conversations.list")
def handle_list_conversations(params: dict[str, Any]) -> dict[str, Any]:
    """List conversations with pagination.

    Params:
        limit: int (default 50)
        offset: int (default 0)
        include_archived: bool (default False)
        search_query: str | None (optional title search)

    Returns:
        {
            "conversations": [...],
            "total_count": int
        }
    """
    manager = get_conversation_manager()

    limit = params.get("limit", 50)
    offset = params.get("offset", 0)
    include_archived = params.get("include_archived", False)
    search_query = params.get("search_query")

    conversations, total_count = manager.list(
        limit=limit,
        offset=offset,
        include_archived=include_archived,
        search_query=search_query,
    )

    return {
        "conversations": [c.to_dict() for c in conversations],
        "total_count": total_count,
    }


@handler("conversations.create")
def handle_create_conversation(params: dict[str, Any]) -> dict[str, Any]:
    """Create a new conversation.

    Params:
        title: str | None (optional, defaults to "New Conversation")

    Returns:
        {"conversation": {...}}
    """
    manager = get_conversation_manager()

    title = params.get("title")
    conversation = manager.create(title=title)

    return {"conversation": conversation.to_dict()}


@handler("conversations.get")
def handle_get_conversation(params: dict[str, Any]) -> dict[str, Any]:
    """Get a conversation with its messages.

    Params:
        conversation_id: str
        message_limit: int (default 50)
        message_offset: int (default 0)

    Returns:
        {
            "conversation": {...},
            "messages": [...],
            "has_more": bool
        }
    """
    manager = get_conversation_manager()

    conversation_id = params.get("conversation_id")
    if not conversation_id:
        raise ValueError("conversation_id is required")

    message_limit = params.get("message_limit", 50)
    message_offset = params.get("message_offset", 0)

    conversation = manager.get(conversation_id)
    if not conversation:
        raise ValueError(f"Conversation not found: {conversation_id}")

    messages = manager.get_messages(
        conversation_id,
        limit=message_limit,
        offset=message_offset,
        order="asc",
    )

    # Check if there are more messages
    total_messages = manager.get_message_count(conversation_id)
    has_more = message_offset + len(messages) < total_messages

    return {
        "conversation": conversation.to_dict(),
        "messages": [m.to_dict() for m in messages],
        "has_more": has_more,
    }


@handler("conversations.update")
def handle_update_conversation(params: dict[str, Any]) -> dict[str, Any]:
    """Update conversation metadata.

    Params:
        conversation_id: str
        title: str | None
        pinned: bool | None
        archived: bool | None

    Returns:
        {"success": bool, "conversation": {...}}
    """
    manager = get_conversation_manager()

    conversation_id = params.get("conversation_id")
    if not conversation_id:
        raise ValueError("conversation_id is required")

    conversation = manager.update(
        conversation_id,
        title=params.get("title"),
        pinned=params.get("pinned"),
        archived=params.get("archived"),
    )

    if not conversation:
        raise ValueError(f"Conversation not found: {conversation_id}")

    return {
        "success": True,
        "conversation": conversation.to_dict(),
    }


@handler("conversations.delete")
def handle_delete_conversation(params: dict[str, Any]) -> dict[str, Any]:
    """Delete a conversation and all its messages.

    Params:
        conversation_id: str

    Returns:
        {"success": bool}
    """
    manager = get_conversation_manager()

    conversation_id = params.get("conversation_id")
    if not conversation_id:
        raise ValueError("conversation_id is required")

    deleted = manager.delete(conversation_id)

    return {"success": deleted}


@handler("conversations.send")
def handle_send_message(params: dict[str, Any]) -> dict[str, Any]:
    """Send a user message and get AI response with conversation context.

    This is the main handler for chat within a conversation. It:
    1. Saves the user message
    2. Builds conversation context
    3. Calls ChatAPI with context
    4. Saves the assistant response
    5. Auto-generates title if first exchange
    6. Updates conversation summary if needed

    Params:
        conversation_id: str
        query: str
        time_filter: str | None
        include_graph_expansion: bool (default True)
        include_aggregates: bool (default True)
        max_results: int (default 10)

    Returns:
        {
            "user_message": {...},
            "assistant_message": {...},
            "response": ChatResponse dict,
            "title_updated": bool,
            "new_title": str | None
        }
    """
    manager = get_conversation_manager()
    context_builder = _get_context_builder()
    api = _get_chat_api()

    conversation_id = params.get("conversation_id")
    query = params.get("query")

    if not conversation_id:
        raise ValueError("conversation_id is required")
    if not query:
        raise ValueError("query is required")

    # Verify conversation exists
    conversation = manager.get(conversation_id)
    if not conversation:
        raise ValueError(f"Conversation not found: {conversation_id}")

    # Save user message
    user_message = manager.add_message(
        conversation_id=conversation_id,
        role="user",
        content=query,
    )

    # Build conversation context (for future use when ChatAPI accepts context)
    _ = context_builder.build_context(conversation_id)

    # Prepare chat request
    request = ChatRequest(
        query=query,
        time_filter_hint=params.get("time_filter"),
        include_graph_expansion=params.get("include_graph_expansion", True),
        include_aggregates=params.get("include_aggregates", True),
        max_results=params.get("max_results", 10),
    )

    # Call ChatAPI with conversation context
    # Note: Context is built but not yet integrated into ChatAPI
    # TODO: Extend ChatAPI to accept conversation_context parameter
    response = api.chat(request)

    # Prepare metadata for assistant message
    metadata = {
        "citations": [c.to_dict() for c in response.citations],
        "notes": [n.to_dict() for n in response.notes],
        "aggregates": [a.to_dict() for a in response.aggregates],
        "confidence": response.confidence,
        "query_type": response.query_type,
        "processing_time_ms": response.processing_time_ms,
    }

    # Save assistant message
    assistant_message = manager.add_message(
        conversation_id=conversation_id,
        role="assistant",
        content=response.answer,
        metadata=metadata,
    )

    # Check if we should auto-generate title
    title_updated = False
    new_title = None

    # Generate title after first exchange if still default
    if conversation.title == "New Conversation" and conversation.message_count <= 1:
        try:
            new_title = generate_conversation_title(
                first_query=query,
                first_response=response.answer[:500],
            )
            if new_title and new_title != "New Conversation":
                manager.update(
                    conversation_id,
                    title=new_title,
                    title_generated_at=datetime.now(),
                )
                title_updated = True
        except Exception as e:
            logger.warning(f"Failed to generate title: {e}")

    # Update summary if needed (async-like, but blocking for now)
    try:
        context_builder.maybe_update_summary(conversation_id)
    except Exception as e:
        logger.warning(f"Failed to update summary: {e}")

    return {
        "user_message": user_message.to_dict(),
        "assistant_message": assistant_message.to_dict(),
        "response": response.to_dict(),
        "title_updated": title_updated,
        "new_title": new_title,
    }


@handler("conversations.generate_title")
def handle_generate_title(params: dict[str, Any]) -> dict[str, Any]:
    """Generate or regenerate a title for a conversation.

    Params:
        conversation_id: str
        force: bool (default False, regenerate even if already has title)

    Returns:
        {"title": str, "generated": bool}
    """
    manager = get_conversation_manager()

    conversation_id = params.get("conversation_id")
    if not conversation_id:
        raise ValueError("conversation_id is required")

    force = params.get("force", False)

    conversation = manager.get(conversation_id)
    if not conversation:
        raise ValueError(f"Conversation not found: {conversation_id}")

    # Check if we should generate
    if not force and conversation.title != "New Conversation":
        return {"title": conversation.title, "generated": False}

    # Get first exchange
    messages = manager.get_messages(conversation_id, limit=2, order="asc")

    if len(messages) < 2:
        return {"title": conversation.title, "generated": False}

    first_query = messages[0].content if messages[0].role == "user" else ""
    first_response = messages[1].content if messages[1].role == "assistant" else ""

    if not first_query:
        return {"title": conversation.title, "generated": False}

    try:
        new_title = generate_conversation_title(
            first_query=first_query,
            first_response=first_response[:500] if first_response else "",
        )

        if new_title and new_title != "New Conversation":
            manager.update(
                conversation_id,
                title=new_title,
                title_generated_at=datetime.now(),
            )
            return {"title": new_title, "generated": True}

    except Exception as e:
        logger.warning(f"Failed to generate title: {e}")

    return {"title": conversation.title, "generated": False}


def reset_conversation_api():
    """Reset the conversation API instances (called when API key changes)."""
    global _chat_api, _context_builder
    _chat_api = None
    _context_builder = None
