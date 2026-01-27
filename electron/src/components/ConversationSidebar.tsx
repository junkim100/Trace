import { useState, useCallback, useRef, useEffect } from 'react';
import { useConversation } from '../contexts/ConversationContext';
import type { Conversation } from '../types/trace-api';

interface ConversationSidebarProps {
  onNewConversation?: () => void;
}

export function ConversationSidebar({ onNewConversation }: ConversationSidebarProps) {
  const {
    conversations,
    currentConversation,
    loading,
    selectConversation,
    startNewConversation,
    renameConversation,
    deleteConversation,
    togglePin,
    archiveConversation,
    isConversationPending,
  } = useConversation();

  const [searchQuery, setSearchQuery] = useState('');
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editTitle, setEditTitle] = useState('');
  const [contextMenu, setContextMenu] = useState<{
    conversationId: string;
    x: number;
    y: number;
  } | null>(null);
  const editInputRef = useRef<HTMLInputElement>(null);

  // Close context menu when clicking elsewhere
  useEffect(() => {
    const handleClick = () => setContextMenu(null);
    document.addEventListener('click', handleClick);
    return () => document.removeEventListener('click', handleClick);
  }, []);

  // Focus edit input when editing
  useEffect(() => {
    if (editingId && editInputRef.current) {
      editInputRef.current.focus();
      editInputRef.current.select();
    }
  }, [editingId]);

  const handleNewConversation = useCallback(() => {
    startNewConversation();
    onNewConversation?.();
  }, [startNewConversation, onNewConversation]);

  const handleContextMenu = useCallback((e: React.MouseEvent, conversationId: string) => {
    e.preventDefault();
    setContextMenu({
      conversationId,
      x: e.clientX,
      y: e.clientY,
    });
  }, []);

  const handleStartRename = useCallback((conversation: Conversation) => {
    setEditingId(conversation.conversation_id);
    setEditTitle(conversation.title);
    setContextMenu(null);
  }, []);

  const handleConfirmRename = useCallback(async () => {
    if (editingId && editTitle.trim()) {
      await renameConversation(editingId, editTitle.trim());
    }
    setEditingId(null);
    setEditTitle('');
  }, [editingId, editTitle, renameConversation]);

  const handleCancelRename = useCallback(() => {
    setEditingId(null);
    setEditTitle('');
  }, []);

  const handleDelete = useCallback(async (conversationId: string) => {
    setContextMenu(null);
    if (window.confirm('Delete this conversation? This cannot be undone.')) {
      await deleteConversation(conversationId);
    }
  }, [deleteConversation]);

  const handleTogglePin = useCallback(async (conversationId: string) => {
    setContextMenu(null);
    await togglePin(conversationId);
  }, [togglePin]);

  const handleArchive = useCallback(async (conversationId: string) => {
    setContextMenu(null);
    await archiveConversation(conversationId);
  }, [archiveConversation]);

  // Filter conversations by search query
  const filteredConversations = conversations.filter(c =>
    c.title.toLowerCase().includes(searchQuery.toLowerCase())
  );

  // Group conversations by time
  const groupedConversations = groupConversationsByTime(filteredConversations);

  return (
    <div style={styles.container}>
      {/* Search input */}
      <div style={styles.searchContainer}>
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" style={styles.searchIcon}>
          <circle cx="11" cy="11" r="8" />
          <path d="M21 21l-4.35-4.35" />
        </svg>
        <input
          type="text"
          placeholder="Search conversations..."
          value={searchQuery}
          onChange={e => setSearchQuery(e.target.value)}
          style={styles.searchInput}
        />
      </div>

      {/* New conversation button */}
      <button
        onClick={handleNewConversation}
        style={styles.newButton}
      >
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
          <line x1="12" y1="5" x2="12" y2="19" />
          <line x1="5" y1="12" x2="19" y2="12" />
        </svg>
        New Conversation
      </button>

      {/* Conversation list */}
      <div style={styles.listContainer}>
        {loading && conversations.length === 0 ? (
          <div style={styles.emptyState}>Loading...</div>
        ) : filteredConversations.length === 0 ? (
          <div style={styles.emptyState}>
            {searchQuery ? 'No matching conversations' : 'No conversations yet'}
          </div>
        ) : (
          Object.entries(groupedConversations).map(([group, convs]) => (
            convs.length > 0 && (
              <div key={group} style={styles.group}>
                <div style={styles.groupHeader}>{group}</div>
                {convs.map(conversation => {
                  const isPending = isConversationPending(conversation.conversation_id);
                  return (
                    <div
                      key={conversation.conversation_id}
                      style={{
                        ...styles.conversationItem,
                        ...(currentConversation?.conversation_id === conversation.conversation_id
                          ? styles.conversationItemActive
                          : {}),
                      }}
                      onClick={() => selectConversation(conversation.conversation_id)}
                      onContextMenu={e => handleContextMenu(e, conversation.conversation_id)}
                    >
                      {/* Status indicators (top right) */}
                      <div style={styles.statusIcons}>
                        {conversation.pinned && (
                          <svg width="12" height="12" viewBox="0 0 24 24" fill="currentColor" style={styles.pinIconInline}>
                            <path d="M16 4l4 4-8.6 8.6-4.3 1.4 1.4-4.3L16 4z" />
                          </svg>
                        )}
                        {isPending && (
                          <div style={styles.pendingSpinner} title="Generating..." />
                        )}
                      </div>
                      {editingId === conversation.conversation_id ? (
                        <input
                          ref={editInputRef}
                          type="text"
                          value={editTitle}
                          onChange={e => setEditTitle(e.target.value)}
                          onKeyDown={e => {
                            if (e.key === 'Enter') handleConfirmRename();
                            if (e.key === 'Escape') handleCancelRename();
                          }}
                          onBlur={handleConfirmRename}
                          style={styles.editInput}
                          onClick={e => e.stopPropagation()}
                        />
                      ) : (
                        <>
                          <span style={styles.conversationTitle}>
                            {conversation.title}
                          </span>
                          <span style={styles.conversationPreview}>
                            {isPending ? (
                              <em style={{ color: 'var(--accent)' }}>Generating...</em>
                            ) : (
                              <>
                                {conversation.last_message_preview?.slice(0, 40) || ''}
                                {(conversation.last_message_preview?.length || 0) > 40 ? '...' : ''}
                              </>
                            )}
                          </span>
                        </>
                      )}
                    </div>
                  );
                })}
              </div>
            )
          ))
        )}
      </div>

      {/* Context menu */}
      {contextMenu && (
        <div
          style={{
            ...styles.contextMenu,
            left: contextMenu.x,
            top: contextMenu.y,
          }}
          onClick={e => e.stopPropagation()}
        >
          <button
            style={styles.contextMenuItem}
            onClick={() => {
              const conv = conversations.find(c => c.conversation_id === contextMenu.conversationId);
              if (conv) handleStartRename(conv);
            }}
          >
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M17 3a2.828 2.828 0 1 1 4 4L7.5 20.5 2 22l1.5-5.5L17 3z" />
            </svg>
            Rename
          </button>
          <button
            style={styles.contextMenuItem}
            onClick={() => handleTogglePin(contextMenu.conversationId)}
          >
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M16 4l4 4-8.6 8.6-4.3 1.4 1.4-4.3L16 4z" />
            </svg>
            {conversations.find(c => c.conversation_id === contextMenu.conversationId)?.pinned
              ? 'Unpin'
              : 'Pin'}
          </button>
          <button
            style={styles.contextMenuItem}
            onClick={() => handleArchive(contextMenu.conversationId)}
          >
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <polyline points="21 8 21 21 3 21 3 8" />
              <rect x="1" y="3" width="22" height="5" />
              <line x1="10" y1="12" x2="14" y2="12" />
            </svg>
            Archive
          </button>
          <div style={styles.contextMenuDivider} />
          <button
            style={{ ...styles.contextMenuItem, ...styles.contextMenuItemDanger }}
            onClick={() => handleDelete(contextMenu.conversationId)}
          >
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <polyline points="3 6 5 6 21 6" />
              <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2" />
            </svg>
            Delete
          </button>
        </div>
      )}
    </div>
  );
}

function groupConversationsByTime(conversations: Conversation[]): Record<string, Conversation[]> {
  const now = new Date();
  const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  const yesterday = new Date(today.getTime() - 24 * 60 * 60 * 1000);
  const lastWeek = new Date(today.getTime() - 7 * 24 * 60 * 60 * 1000);
  const lastMonth = new Date(today.getTime() - 30 * 24 * 60 * 60 * 1000);

  const groups: Record<string, Conversation[]> = {
    'Pinned': [],
    'Today': [],
    'Yesterday': [],
    'Last 7 Days': [],
    'Last 30 Days': [],
    'Older': [],
  };

  for (const conv of conversations) {
    if (conv.pinned) {
      groups['Pinned'].push(conv);
      continue;
    }

    const date = new Date(conv.updated_ts);
    if (date >= today) {
      groups['Today'].push(conv);
    } else if (date >= yesterday) {
      groups['Yesterday'].push(conv);
    } else if (date >= lastWeek) {
      groups['Last 7 Days'].push(conv);
    } else if (date >= lastMonth) {
      groups['Last 30 Days'].push(conv);
    } else {
      groups['Older'].push(conv);
    }
  }

  return groups;
}

const styles: Record<string, React.CSSProperties> = {
  container: {
    display: 'flex',
    flexDirection: 'column',
    height: '100%',
    overflow: 'hidden',
  },
  searchContainer: {
    position: 'relative',
    marginBottom: '0.75rem',
  },
  searchIcon: {
    position: 'absolute',
    left: '0.75rem',
    top: '50%',
    transform: 'translateY(-50%)',
    color: 'var(--text-secondary)',
    pointerEvents: 'none',
  },
  searchInput: {
    width: '100%',
    padding: '0.625rem 0.75rem 0.625rem 2.25rem',
    backgroundColor: 'var(--bg-secondary)',
    border: '1px solid var(--border)',
    borderRadius: '8px',
    fontSize: '0.875rem',
    color: 'var(--text-primary)',
    outline: 'none',
    boxSizing: 'border-box',
  },
  newButton: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    gap: '0.5rem',
    padding: '0.75rem',
    backgroundColor: 'var(--accent)',
    border: 'none',
    borderRadius: '8px',
    fontSize: '0.875rem',
    fontWeight: 500,
    color: 'white',
    cursor: 'pointer',
    marginBottom: '1rem',
    transition: 'opacity 0.2s',
  },
  listContainer: {
    flex: 1,
    overflowY: 'auto',
    overflowX: 'hidden',
    marginRight: '-0.5rem',
    paddingRight: '0.5rem',
  },
  emptyState: {
    textAlign: 'center',
    color: 'var(--text-secondary)',
    fontSize: '0.875rem',
    padding: '2rem 1rem',
  },
  group: {
    marginBottom: '1rem',
  },
  groupHeader: {
    fontSize: '0.7rem',
    fontWeight: 600,
    color: 'var(--text-secondary)',
    textTransform: 'uppercase',
    letterSpacing: '0.05em',
    padding: '0.25rem 0.5rem',
    marginBottom: '0.25rem',
  },
  conversationItem: {
    display: 'flex',
    flexDirection: 'column',
    gap: '0.125rem',
    padding: '0.625rem 0.75rem',
    borderRadius: '6px',
    cursor: 'pointer',
    transition: 'background-color 0.15s',
    position: 'relative',
  },
  conversationItemActive: {
    backgroundColor: 'var(--bg-secondary)',
    border: '1px solid var(--border)',
    margin: '-1px',
    padding: 'calc(0.625rem + 1px) calc(0.75rem + 1px)',
  },
  conversationTitle: {
    fontSize: '0.875rem',
    color: 'var(--text-primary)',
    overflow: 'hidden',
    textOverflow: 'ellipsis',
    whiteSpace: 'nowrap',
    paddingLeft: '0',
  },
  conversationPreview: {
    fontSize: '0.75rem',
    color: 'var(--text-secondary)',
    overflow: 'hidden',
    textOverflow: 'ellipsis',
    whiteSpace: 'nowrap',
  },
  statusIcons: {
    position: 'absolute',
    top: '0.5rem',
    right: '0.5rem',
    display: 'flex',
    alignItems: 'center',
    gap: '0.25rem',
  },
  pinIconInline: {
    color: 'var(--accent)',
    opacity: 0.7,
  },
  pendingSpinner: {
    width: '10px',
    height: '10px',
    border: '2px solid var(--border)',
    borderTopColor: 'var(--accent)',
    borderRadius: '50%',
    animation: 'spin 0.8s linear infinite',
  },
  pinIcon: {
    position: 'absolute',
    top: '0.5rem',
    right: '0.5rem',
    color: 'var(--accent)',
    opacity: 0.7,
  },
  editInput: {
    width: '100%',
    padding: '0.25rem 0.5rem',
    backgroundColor: 'var(--bg-primary)',
    border: '1px solid var(--accent)',
    borderRadius: '4px',
    fontSize: '0.875rem',
    color: 'var(--text-primary)',
    outline: 'none',
  },
  contextMenu: {
    position: 'fixed',
    backgroundColor: 'var(--bg-secondary)',
    border: '1px solid var(--border)',
    borderRadius: '8px',
    padding: '0.375rem',
    boxShadow: '0 4px 12px rgba(0, 0, 0, 0.15)',
    zIndex: 1000,
    minWidth: '140px',
  },
  contextMenuItem: {
    display: 'flex',
    alignItems: 'center',
    gap: '0.5rem',
    width: '100%',
    padding: '0.5rem 0.75rem',
    backgroundColor: 'transparent',
    border: 'none',
    borderRadius: '4px',
    fontSize: '0.8rem',
    color: 'var(--text-primary)',
    cursor: 'pointer',
    textAlign: 'left',
  },
  contextMenuItemDanger: {
    color: '#ff3b30',
  },
  contextMenuDivider: {
    height: '1px',
    backgroundColor: 'var(--border)',
    margin: '0.375rem 0',
  },
};

export default ConversationSidebar;
