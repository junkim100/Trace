import { useEffect, useRef, useCallback } from 'react';
import { useConversation } from '../contexts/ConversationContext';
import type { ConversationMessage, MessageMetadata } from '../types/trace-api';

interface MessageThreadProps {
  onCitationClick?: (noteId: string) => void;
  onSuggestionClick?: (query: string) => void;
}

export function MessageThread({ onCitationClick, onSuggestionClick }: MessageThreadProps) {
  const {
    messages,
    currentConversation,
    sending,
    loading,
    hasMoreMessages,
    loadMoreMessages,
  } = useConversation();

  const containerRef = useRef<HTMLDivElement>(null);
  const bottomRef = useRef<HTMLDivElement>(null);
  const prevMessagesLength = useRef(messages.length);

  // Auto-scroll to bottom when new messages arrive
  useEffect(() => {
    if (messages.length > prevMessagesLength.current) {
      bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
    }
    prevMessagesLength.current = messages.length;
  }, [messages.length]);

  // Scroll to bottom when conversation changes
  useEffect(() => {
    if (currentConversation) {
      setTimeout(() => {
        bottomRef.current?.scrollIntoView({ behavior: 'auto' });
      }, 50);
    }
  }, [currentConversation?.conversation_id]);

  const handleScroll = useCallback(() => {
    if (!containerRef.current || loading || !hasMoreMessages) return;

    // Load more when scrolled to top
    if (containerRef.current.scrollTop === 0) {
      loadMoreMessages();
    }
  }, [loading, hasMoreMessages, loadMoreMessages]);

  // Empty state when no conversation selected
  if (!currentConversation && messages.length === 0) {
    return (
      <div style={styles.emptyContainer}>
        <div style={styles.emptyContent}>
          <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" style={styles.emptyIcon}>
            <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
          </svg>
          <h3 style={styles.emptyTitle}>Start a Conversation</h3>
          <p style={styles.emptyText}>
            Ask about your activity, search your notes, or explore patterns in your data.
          </p>
          <div style={styles.suggestions}>
            <span style={styles.suggestionLabel}>Try asking:</span>
            <div style={styles.suggestionList}>
              {[
                "What did I work on today?",
                "Summarize my activity this week",
                "What topics have I been researching lately?",
              ].map((suggestion) => (
                <button
                  key={suggestion}
                  style={styles.suggestionItem}
                  onClick={() => onSuggestionClick?.(suggestion)}
                >
                  {suggestion}
                </button>
              ))}
            </div>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div
      ref={containerRef}
      style={styles.container}
      onScroll={handleScroll}
    >
      {/* Load more indicator */}
      {hasMoreMessages && (
        <div style={styles.loadMore}>
          <button
            onClick={loadMoreMessages}
            disabled={loading}
            style={styles.loadMoreButton}
          >
            {loading ? 'Loading...' : 'Load earlier messages'}
          </button>
        </div>
      )}

      {/* Messages */}
      <div style={styles.messages}>
        {messages.map((message, idx) => (
          <MessageBubble
            key={message.message_id}
            message={message}
            onCitationClick={onCitationClick}
            isLast={idx === messages.length - 1}
          />
        ))}

        {/* Sending indicator */}
        {sending && (
          <div style={styles.sendingIndicator}>
            <div style={styles.sendingDot} />
            <div style={{ ...styles.sendingDot, animationDelay: '0.2s' }} />
            <div style={{ ...styles.sendingDot, animationDelay: '0.4s' }} />
          </div>
        )}
      </div>

      <div ref={bottomRef} />
    </div>
  );
}

interface MessageBubbleProps {
  message: ConversationMessage;
  onCitationClick?: (noteId: string) => void;
  isLast: boolean;
}

function MessageBubble({ message, onCitationClick, isLast: _isLast }: MessageBubbleProps) {
  const isUser = message.role === 'user';
  const metadata = message.metadata as MessageMetadata | null;

  return (
    <div style={{
      ...styles.messageBubble,
      ...(isUser ? styles.userBubble : styles.assistantBubble),
    }}>
      {/* Role indicator */}
      <div style={styles.roleIndicator}>
        {isUser ? (
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2" />
            <circle cx="12" cy="7" r="4" />
          </svg>
        ) : (
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <circle cx="12" cy="12" r="10" />
            <path d="M12 16v-4" />
            <path d="M12 8h.01" />
          </svg>
        )}
        <span style={styles.roleLabel}>{isUser ? 'You' : 'Trace'}</span>
        <span style={styles.timestamp}>
          {formatTimestamp(message.created_ts)}
        </span>
      </div>

      {/* Message content */}
      <div style={styles.messageContent}>
        <p style={styles.messageText}>{message.content}</p>
      </div>

      {/* Assistant message metadata */}
      {!isUser && metadata && (
        <div style={styles.metadata}>
          {/* Citations */}
          {metadata.citations && metadata.citations.length > 0 && (
            <div style={styles.citations}>
              <span style={styles.citationsLabel}>Sources:</span>
              <div style={styles.citationsList}>
                {metadata.citations.map((citation, idx) => (
                  <button
                    key={idx}
                    onClick={() => onCitationClick?.(citation.note_id)}
                    style={styles.citationButton}
                    title={`${citation.note_type} note`}
                  >
                    {citation.label || formatCitationLabel(citation.timestamp)}
                  </button>
                ))}
              </div>
            </div>
          )}

          {/* Confidence and processing time */}
          <div style={styles.metaStats}>
            {metadata.confidence !== undefined && (
              <span style={styles.metaStat}>
                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14" />
                  <polyline points="22 4 12 14.01 9 11.01" />
                </svg>
                {Math.round(metadata.confidence * 100)}%
              </span>
            )}
            {metadata.processing_time_ms !== undefined && (
              <span style={styles.metaStat}>
                {metadata.processing_time_ms.toFixed(0)}ms
              </span>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

function formatTimestamp(isoString: string): string {
  try {
    const date = new Date(isoString);
    const now = new Date();
    const isToday = date.toDateString() === now.toDateString();

    if (isToday) {
      return date.toLocaleTimeString('en-US', {
        hour: 'numeric',
        minute: '2-digit',
      });
    }

    return date.toLocaleDateString('en-US', {
      month: 'short',
      day: 'numeric',
      hour: 'numeric',
      minute: '2-digit',
    });
  } catch {
    return '';
  }
}

function formatCitationLabel(timestamp: string): string {
  try {
    const date = new Date(timestamp);
    return date.toLocaleDateString('en-US', {
      weekday: 'short',
      month: 'short',
      day: 'numeric',
      hour: 'numeric',
      minute: '2-digit',
    });
  } catch {
    return 'Note';
  }
}

const styles: Record<string, React.CSSProperties> = {
  container: {
    flex: 1,
    overflowY: 'auto',
    overflowX: 'hidden',
    padding: '1rem 1.5rem',
    display: 'flex',
    flexDirection: 'column',
  },
  emptyContainer: {
    flex: 1,
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    padding: '2rem',
  },
  emptyContent: {
    textAlign: 'center',
    maxWidth: '400px',
  },
  emptyIcon: {
    opacity: 0.3,
    marginBottom: '1rem',
  },
  emptyTitle: {
    fontSize: '1.25rem',
    fontWeight: 600,
    color: 'var(--text-primary)',
    marginBottom: '0.5rem',
  },
  emptyText: {
    fontSize: '0.95rem',
    color: 'var(--text-secondary)',
    lineHeight: 1.5,
    marginBottom: '1.5rem',
  },
  suggestions: {
    display: 'flex',
    flexDirection: 'column',
    gap: '0.5rem',
    alignItems: 'center',
  },
  suggestionLabel: {
    fontSize: '0.8rem',
    color: 'var(--text-secondary)',
  },
  suggestionList: {
    display: 'flex',
    flexDirection: 'column',
    gap: '0.375rem',
  },
  suggestionItem: {
    fontSize: '0.85rem',
    color: 'var(--accent)',
    backgroundColor: 'rgba(0, 122, 255, 0.1)',
    padding: '0.5rem 0.75rem',
    borderRadius: '6px',
    border: 'none',
    cursor: 'pointer',
    transition: 'background-color 0.2s, transform 0.1s',
    textAlign: 'left' as const,
  },
  loadMore: {
    textAlign: 'center',
    padding: '0.5rem',
    marginBottom: '1rem',
  },
  loadMoreButton: {
    backgroundColor: 'transparent',
    border: '1px solid var(--border)',
    borderRadius: '6px',
    padding: '0.5rem 1rem',
    fontSize: '0.8rem',
    color: 'var(--text-secondary)',
    cursor: 'pointer',
  },
  messages: {
    display: 'flex',
    flexDirection: 'column',
    gap: '1.25rem',
    flex: 1,
  },
  messageBubble: {
    display: 'flex',
    flexDirection: 'column',
    maxWidth: '85%',
  },
  userBubble: {
    alignSelf: 'flex-end',
  },
  assistantBubble: {
    alignSelf: 'flex-start',
  },
  roleIndicator: {
    display: 'flex',
    alignItems: 'center',
    gap: '0.375rem',
    marginBottom: '0.375rem',
    color: 'var(--text-secondary)',
  },
  roleLabel: {
    fontSize: '0.75rem',
    fontWeight: 500,
  },
  timestamp: {
    fontSize: '0.7rem',
    opacity: 0.7,
    marginLeft: 'auto',
  },
  messageContent: {
    padding: '0.875rem 1rem',
    borderRadius: '12px',
    backgroundColor: 'var(--bg-secondary)',
    border: '1px solid var(--border)',
  },
  messageText: {
    fontSize: '0.95rem',
    lineHeight: 1.5,
    color: 'var(--text-primary)',
    whiteSpace: 'pre-wrap',
    margin: 0,
  },
  metadata: {
    marginTop: '0.5rem',
    display: 'flex',
    flexDirection: 'column',
    gap: '0.5rem',
  },
  citations: {
    display: 'flex',
    flexDirection: 'column',
    gap: '0.375rem',
  },
  citationsLabel: {
    fontSize: '0.7rem',
    color: 'var(--text-secondary)',
    textTransform: 'uppercase',
    letterSpacing: '0.05em',
  },
  citationsList: {
    display: 'flex',
    flexWrap: 'wrap',
    gap: '0.375rem',
  },
  citationButton: {
    backgroundColor: 'rgba(0, 122, 255, 0.1)',
    border: '1px solid rgba(0, 122, 255, 0.2)',
    borderRadius: '4px',
    padding: '0.25rem 0.5rem',
    fontSize: '0.7rem',
    color: 'var(--accent)',
    cursor: 'pointer',
    transition: 'background-color 0.2s',
  },
  metaStats: {
    display: 'flex',
    gap: '0.75rem',
  },
  metaStat: {
    display: 'flex',
    alignItems: 'center',
    gap: '0.25rem',
    fontSize: '0.7rem',
    color: 'var(--text-secondary)',
  },
  sendingIndicator: {
    display: 'flex',
    gap: '0.25rem',
    padding: '1rem',
    alignSelf: 'flex-start',
  },
  sendingDot: {
    width: '8px',
    height: '8px',
    borderRadius: '50%',
    backgroundColor: 'var(--accent)',
    animation: 'pulse 1s ease-in-out infinite',
  },
};

export default MessageThread;
