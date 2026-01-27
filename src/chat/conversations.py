"""
Conversation Management for Trace Chat

Provides persistent storage and retrieval of chat conversations and messages.
Conversations can be created, listed, updated, and deleted. Messages are
stored with metadata for assistant responses (citations, notes, etc.).
"""

from __future__ import annotations

import json
import logging
import uuid
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

from src.core.paths import DB_PATH
from src.db.migrations import get_connection

logger = logging.getLogger(__name__)


@dataclass
class Conversation:
    """A chat conversation session."""

    conversation_id: str
    title: str
    created_ts: datetime
    updated_ts: datetime
    pinned: bool = False
    archived: bool = False
    title_generated_at: datetime | None = None
    message_count: int = 0
    last_message_preview: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "conversation_id": self.conversation_id,
            "title": self.title,
            "created_ts": self.created_ts.isoformat(),
            "updated_ts": self.updated_ts.isoformat(),
            "pinned": self.pinned,
            "archived": self.archived,
            "title_generated_at": (
                self.title_generated_at.isoformat() if self.title_generated_at else None
            ),
            "message_count": self.message_count,
            "last_message_preview": self.last_message_preview,
        }

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> Conversation:
        """Create from database row."""
        return cls(
            conversation_id=row["conversation_id"],
            title=row["title"],
            created_ts=datetime.fromisoformat(row["created_ts"]),
            updated_ts=datetime.fromisoformat(row["updated_ts"]),
            pinned=bool(row.get("pinned", 0)),
            archived=bool(row.get("archived", 0)),
            title_generated_at=(
                datetime.fromisoformat(row["title_generated_at"])
                if row.get("title_generated_at")
                else None
            ),
            message_count=row.get("message_count", 0),
            last_message_preview=row.get("last_message_preview", ""),
        )


@dataclass
class Message:
    """A message within a conversation."""

    message_id: str
    conversation_id: str
    role: Literal["user", "assistant"]
    content: str
    created_ts: datetime
    metadata: dict[str, Any] | None = None
    token_count: int | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "message_id": self.message_id,
            "conversation_id": self.conversation_id,
            "role": self.role,
            "content": self.content,
            "created_ts": self.created_ts.isoformat(),
            "metadata": self.metadata,
            "token_count": self.token_count,
        }

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> Message:
        """Create from database row."""
        metadata = None
        if row.get("metadata_json"):
            try:
                metadata = json.loads(row["metadata_json"])
            except json.JSONDecodeError:
                pass

        return cls(
            message_id=row["message_id"],
            conversation_id=row["conversation_id"],
            role=row["role"],
            content=row["content"],
            created_ts=datetime.fromisoformat(row["created_ts"]),
            metadata=metadata,
            token_count=row.get("token_count"),
        )


@dataclass
class ConversationContext:
    """Context information for a conversation."""

    conversation_id: str
    summary_text: str | None = None
    summary_token_count: int | None = None
    last_summarized_at: datetime | None = None

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> ConversationContext:
        """Create from database row."""
        return cls(
            conversation_id=row["conversation_id"],
            summary_text=row.get("summary_text"),
            summary_token_count=row.get("summary_token_count"),
            last_summarized_at=(
                datetime.fromisoformat(row["last_summarized_at"])
                if row.get("last_summarized_at")
                else None
            ),
        )


class ConversationManager:
    """
    Manages conversation persistence in SQLite.

    Provides CRUD operations for conversations and messages,
    plus context retrieval for LLM calls.
    """

    def __init__(self, db_path: Path | str | None = None):
        """Initialize the conversation manager.

        Args:
            db_path: Path to SQLite database (defaults to DB_PATH)
        """
        self.db_path = Path(db_path) if db_path else DB_PATH

    def _get_connection(self):
        """Get a database connection."""
        return get_connection(self.db_path)

    # ========== Conversation CRUD ==========

    def create(self, title: str | None = None) -> Conversation:
        """Create a new conversation.

        Args:
            title: Optional title (defaults to "New Conversation")

        Returns:
            The created Conversation
        """
        conversation_id = str(uuid.uuid4())
        now = datetime.now()
        title = title or "New Conversation"

        conn = self._get_connection()
        try:
            conn.execute(
                """
                INSERT INTO conversations (conversation_id, title, created_ts, updated_ts)
                VALUES (?, ?, ?, ?)
                """,
                (conversation_id, title, now.isoformat(), now.isoformat()),
            )
            conn.commit()

            return Conversation(
                conversation_id=conversation_id,
                title=title,
                created_ts=now,
                updated_ts=now,
            )
        finally:
            conn.close()

    def get(self, conversation_id: str) -> Conversation | None:
        """Get a conversation by ID.

        Args:
            conversation_id: The conversation ID

        Returns:
            The Conversation or None if not found
        """
        conn = self._get_connection()
        try:
            cursor = conn.execute(
                """
                SELECT c.*,
                    (SELECT COUNT(*) FROM messages m WHERE m.conversation_id = c.conversation_id) as message_count,
                    (SELECT content FROM messages m WHERE m.conversation_id = c.conversation_id
                     ORDER BY created_ts DESC LIMIT 1) as last_message_preview
                FROM conversations c
                WHERE c.conversation_id = ?
                """,
                (conversation_id,),
            )
            row = cursor.fetchone()
            return Conversation.from_row(dict(row)) if row else None
        finally:
            conn.close()

    def list(
        self,
        limit: int = 50,
        offset: int = 0,
        include_archived: bool = False,
        search_query: str | None = None,
    ) -> tuple[list[Conversation], int]:
        """List conversations with pagination.

        Args:
            limit: Maximum number to return
            offset: Number to skip
            include_archived: Whether to include archived conversations
            search_query: Optional search string for title

        Returns:
            Tuple of (conversations list, total count)
        """
        conn = self._get_connection()
        try:
            # Build WHERE clause
            conditions = []
            params: list[Any] = []

            if not include_archived:
                conditions.append("c.archived = 0")

            if search_query:
                conditions.append("c.title LIKE ?")
                params.append(f"%{search_query}%")

            where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""

            # Get total count
            count_cursor = conn.execute(
                f"SELECT COUNT(*) FROM conversations c {where_clause}",
                params,
            )
            total_count = count_cursor.fetchone()[0]

            # Get conversations with message info
            query = f"""
                SELECT c.*,
                    (SELECT COUNT(*) FROM messages m WHERE m.conversation_id = c.conversation_id) as message_count,
                    (SELECT content FROM messages m WHERE m.conversation_id = c.conversation_id
                     ORDER BY created_ts DESC LIMIT 1) as last_message_preview
                FROM conversations c
                {where_clause}
                ORDER BY c.pinned DESC, c.updated_ts DESC
                LIMIT ? OFFSET ?
            """
            params.extend([limit, offset])

            cursor = conn.execute(query, params)
            conversations = [Conversation.from_row(dict(row)) for row in cursor.fetchall()]

            return conversations, total_count
        finally:
            conn.close()

    def update(
        self,
        conversation_id: str,
        title: str | None = None,
        pinned: bool | None = None,
        archived: bool | None = None,
        title_generated_at: datetime | None = None,
    ) -> Conversation | None:
        """Update a conversation's metadata.

        Args:
            conversation_id: The conversation ID
            title: New title (if provided)
            pinned: New pinned state (if provided)
            archived: New archived state (if provided)
            title_generated_at: Timestamp when title was auto-generated

        Returns:
            The updated Conversation or None if not found
        """
        updates = []
        params: list[Any] = []

        if title is not None:
            updates.append("title = ?")
            params.append(title)

        if pinned is not None:
            updates.append("pinned = ?")
            params.append(1 if pinned else 0)

        if archived is not None:
            updates.append("archived = ?")
            params.append(1 if archived else 0)

        if title_generated_at is not None:
            updates.append("title_generated_at = ?")
            params.append(title_generated_at.isoformat())
        elif title is not None:
            # Clear title_generated_at when user manually sets title
            updates.append("title_generated_at = NULL")

        if not updates:
            return self.get(conversation_id)

        updates.append("updated_ts = ?")
        params.append(datetime.now().isoformat())
        params.append(conversation_id)

        conn = self._get_connection()
        try:
            conn.execute(
                f"UPDATE conversations SET {', '.join(updates)} WHERE conversation_id = ?",
                params,
            )
            conn.commit()
            return self.get(conversation_id)
        finally:
            conn.close()

    def delete(self, conversation_id: str) -> bool:
        """Delete a conversation and all its messages.

        Args:
            conversation_id: The conversation ID

        Returns:
            True if deleted, False if not found
        """
        conn = self._get_connection()
        try:
            cursor = conn.execute(
                "DELETE FROM conversations WHERE conversation_id = ?",
                (conversation_id,),
            )
            conn.commit()
            return cursor.rowcount > 0
        finally:
            conn.close()

    def touch(self, conversation_id: str) -> None:
        """Update the conversation's updated_ts to now.

        Args:
            conversation_id: The conversation ID
        """
        conn = self._get_connection()
        try:
            conn.execute(
                "UPDATE conversations SET updated_ts = ? WHERE conversation_id = ?",
                (datetime.now().isoformat(), conversation_id),
            )
            conn.commit()
        finally:
            conn.close()

    # ========== Message Operations ==========

    def add_message(
        self,
        conversation_id: str,
        role: Literal["user", "assistant"],
        content: str,
        metadata: dict[str, Any] | None = None,
        token_count: int | None = None,
    ) -> Message:
        """Add a message to a conversation.

        Args:
            conversation_id: The conversation ID
            role: "user" or "assistant"
            content: Message content
            metadata: Optional metadata (for assistant messages)
            token_count: Optional token count

        Returns:
            The created Message
        """
        message_id = str(uuid.uuid4())
        now = datetime.now()
        metadata_json = json.dumps(metadata) if metadata else None

        conn = self._get_connection()
        try:
            conn.execute(
                """
                INSERT INTO messages (message_id, conversation_id, role, content, created_ts, metadata_json, token_count)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    message_id,
                    conversation_id,
                    role,
                    content,
                    now.isoformat(),
                    metadata_json,
                    token_count,
                ),
            )
            # Update conversation's updated_ts
            conn.execute(
                "UPDATE conversations SET updated_ts = ? WHERE conversation_id = ?",
                (now.isoformat(), conversation_id),
            )
            conn.commit()

            return Message(
                message_id=message_id,
                conversation_id=conversation_id,
                role=role,
                content=content,
                created_ts=now,
                metadata=metadata,
                token_count=token_count,
            )
        finally:
            conn.close()

    def get_messages(
        self,
        conversation_id: str,
        limit: int = 50,
        offset: int = 0,
        order: Literal["asc", "desc"] = "asc",
    ) -> list[Message]:
        """Get messages for a conversation.

        Args:
            conversation_id: The conversation ID
            limit: Maximum number to return
            offset: Number to skip
            order: Sort order ("asc" for oldest first, "desc" for newest first)

        Returns:
            List of Messages
        """
        conn = self._get_connection()
        try:
            order_dir = "ASC" if order == "asc" else "DESC"
            cursor = conn.execute(
                f"""
                SELECT * FROM messages
                WHERE conversation_id = ?
                ORDER BY created_ts {order_dir}
                LIMIT ? OFFSET ?
                """,
                (conversation_id, limit, offset),
            )
            return [Message.from_row(dict(row)) for row in cursor.fetchall()]
        finally:
            conn.close()

    def get_message_count(self, conversation_id: str) -> int:
        """Get the number of messages in a conversation.

        Args:
            conversation_id: The conversation ID

        Returns:
            Number of messages
        """
        conn = self._get_connection()
        try:
            cursor = conn.execute(
                "SELECT COUNT(*) FROM messages WHERE conversation_id = ?",
                (conversation_id,),
            )
            return cursor.fetchone()[0]
        finally:
            conn.close()

    def get_recent_messages(
        self,
        conversation_id: str,
        max_messages: int = 10,
    ) -> list[Message]:
        """Get the most recent messages for context building.

        Args:
            conversation_id: The conversation ID
            max_messages: Maximum number of messages

        Returns:
            List of Messages (oldest first within the limit)
        """
        conn = self._get_connection()
        try:
            # Get newest N messages, then reverse to get oldest-first order
            cursor = conn.execute(
                """
                SELECT * FROM (
                    SELECT * FROM messages
                    WHERE conversation_id = ?
                    ORDER BY created_ts DESC
                    LIMIT ?
                ) ORDER BY created_ts ASC
                """,
                (conversation_id, max_messages),
            )
            return [Message.from_row(dict(row)) for row in cursor.fetchall()]
        finally:
            conn.close()

    # ========== Context Management ==========

    def get_context(self, conversation_id: str) -> ConversationContext | None:
        """Get the context record for a conversation.

        Args:
            conversation_id: The conversation ID

        Returns:
            ConversationContext or None
        """
        conn = self._get_connection()
        try:
            cursor = conn.execute(
                "SELECT * FROM conversation_context WHERE conversation_id = ?",
                (conversation_id,),
            )
            row = cursor.fetchone()
            return ConversationContext.from_row(dict(row)) if row else None
        finally:
            conn.close()

    def update_context(
        self,
        conversation_id: str,
        summary_text: str,
        summary_token_count: int,
    ) -> None:
        """Update or create the context record for a conversation.

        Args:
            conversation_id: The conversation ID
            summary_text: The summary text
            summary_token_count: Token count of the summary
        """
        now = datetime.now().isoformat()
        conn = self._get_connection()
        try:
            conn.execute(
                """
                INSERT INTO conversation_context (conversation_id, summary_text, summary_token_count, last_summarized_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(conversation_id) DO UPDATE SET
                    summary_text = excluded.summary_text,
                    summary_token_count = excluded.summary_token_count,
                    last_summarized_at = excluded.last_summarized_at
                """,
                (conversation_id, summary_text, summary_token_count, now),
            )
            conn.commit()
        finally:
            conn.close()


# Singleton instance
_manager: ConversationManager | None = None


def get_conversation_manager(db_path: Path | str | None = None) -> ConversationManager:
    """Get the global ConversationManager instance.

    Args:
        db_path: Optional database path override

    Returns:
        ConversationManager instance
    """
    global _manager
    if _manager is None or db_path:
        _manager = ConversationManager(db_path)
    return _manager
