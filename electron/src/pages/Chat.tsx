import { useState, useCallback, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { ChatInput } from '../components/ChatInput';
import { TimeFilter, TimePreset, getTimeFilterHint } from '../components/TimeFilter';
import { Sources } from '../components/Sources';
import { NoteViewer } from '../components/NoteViewer';
import { ConversationSidebar } from '../components/ConversationSidebar';
import { MessageThread } from '../components/MessageThread';
import { ConversationProvider, useConversation } from '../contexts/ConversationContext';
import type { ConversationSendResponse } from '../types/trace-api';

function ChatContent() {
  const navigate = useNavigate();
  const {
    currentConversation,
    sending,
    error,
    sendMessage,
    clearError,
  } = useConversation();

  const [timePreset, setTimePreset] = useState<TimePreset>('all');
  const [customStart, setCustomStart] = useState<string>();
  const [customEnd, setCustomEnd] = useState<string>();
  const [selectedNoteId, setSelectedNoteId] = useState<string | null>(null);
  const [lastResponse, setLastResponse] = useState<ConversationSendResponse | null>(null);
  const [apiKeyMissing, setApiKeyMissing] = useState<boolean>(false);

  // Check for API key on mount
  useEffect(() => {
    const checkApiKey = async () => {
      try {
        const settings = await window.traceAPI?.settings?.get();
        if (!settings?.has_api_key) {
          setApiKeyMissing(true);
        }
      } catch (err) {
        console.error('Failed to check API key:', err);
      }
    };
    checkApiKey();
  }, []);

  const handleQuery = useCallback(async (query: string) => {
    clearError();

    const timeFilter = getTimeFilterHint(timePreset, customStart, customEnd);
    const result = await sendMessage(query, {
      timeFilter,
      includeGraphExpansion: true,
      includeAggregates: true,
      maxResults: 10,
    });

    if (result) {
      setLastResponse(result);
    }

    // Check for API key errors and redirect
    if (error) {
      const isApiKeyError =
        error.toLowerCase().includes('invalid api key') ||
        error.toLowerCase().includes('api key') ||
        error.includes('401') ||
        error.toLowerCase().includes('authentication') ||
        error.toLowerCase().includes('unauthorized');

      if (isApiKeyError) {
        navigate('/');
        return;
      }
    }
  }, [timePreset, customStart, customEnd, sendMessage, clearError, error, navigate]);

  const handleTimeFilterChange = useCallback((
    preset: TimePreset,
    start?: string,
    end?: string
  ) => {
    setTimePreset(preset);
    setCustomStart(start);
    setCustomEnd(end);
  }, []);

  // Get citations from the last response for the sidebar
  const citations = lastResponse?.response?.unified_citations || [];

  return (
    <div style={styles.container}>
      {/* Titlebar area for dragging */}
      <div className="titlebar" style={styles.titlebar}>
        <div style={styles.titlebarSpacer} />
        <button
          onClick={() => navigate('/dashboard')}
          style={styles.settingsButton}
          title="Activity Dashboard"
        >
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <rect x="3" y="3" width="7" height="7" />
            <rect x="14" y="3" width="7" height="7" />
            <rect x="3" y="14" width="7" height="7" />
            <rect x="14" y="14" width="7" height="7" />
          </svg>
        </button>
        <button
          onClick={() => navigate('/graph')}
          style={styles.settingsButton}
          title="Knowledge Graph"
        >
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <circle cx="6" cy="6" r="3" />
            <circle cx="18" cy="6" r="3" />
            <circle cx="6" cy="18" r="3" />
            <circle cx="18" cy="18" r="3" />
            <line x1="8.5" y1="7.5" x2="15.5" y2="16.5" />
            <line x1="15.5" y1="7.5" x2="8.5" y2="16.5" />
          </svg>
        </button>
        <button
          onClick={() => navigate('/settings')}
          style={styles.settingsButton}
          title="Settings"
        >
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <circle cx="12" cy="12" r="3" />
            <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z" />
          </svg>
        </button>
      </div>

      <main style={styles.main}>
        {/* Conversations Sidebar (left) */}
        <div style={styles.conversationsSidebar}>
          <ConversationSidebar />
          {/* Logo at bottom */}
          <div style={styles.sidebarFooter}>
            <span style={styles.logoText}>TRACE</span>
          </div>
        </div>

        {/* Chat content (center) */}
        <div style={styles.chatContent}>
          {/* Message thread */}
          <div style={styles.messageArea}>
            <MessageThread onCitationClick={setSelectedNoteId} onSuggestionClick={handleQuery} />
          </div>

          {/* Error display */}
          {error && (
            <div style={styles.errorBanner}>
              <span>{error}</span>
              <button onClick={clearError} style={styles.errorDismiss}>
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <line x1="18" y1="6" x2="6" y2="18" />
                  <line x1="6" y1="6" x2="18" y2="18" />
                </svg>
              </button>
            </div>
          )}

          {/* API key missing warning */}
          {apiKeyMissing && (
            <div style={styles.apiKeyWarning}>
              <div style={styles.apiKeyWarningContent}>
                <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z" />
                  <line x1="12" y1="9" x2="12" y2="13" />
                  <line x1="12" y1="17" x2="12.01" y2="17" />
                </svg>
                <div>
                  <strong>OpenAI API Key Required</strong>
                  <p style={{ margin: '0.25rem 0 0', fontSize: '0.85rem' }}>
                    Add your API key in Settings to start chatting.
                  </p>
                </div>
                <button
                  onClick={() => navigate('/settings')}
                  style={styles.apiKeyWarningButton}
                >
                  Open Settings
                </button>
              </div>
            </div>
          )}

          {/* Chat input with time filter */}
          <div style={styles.inputArea}>
            <div style={styles.inputRow}>
              <TimeFilter
                value={timePreset}
                customStart={customStart}
                customEnd={customEnd}
                onChange={handleTimeFilterChange}
                compact
              />
            </div>
            <ChatInput
              onSubmit={handleQuery}
              disabled={sending || apiKeyMissing}
              placeholder={
                apiKeyMissing
                  ? "Add OpenAI API key in Settings to chat"
                  : currentConversation
                    ? "Continue the conversation..."
                    : "Ask about your activity..."
              }
            />
          </div>
        </div>

        {/* Sources sidebar (right) */}
        <div style={styles.resultsSidebar}>
          <Sources
            citations={citations}
            onNoteClick={setSelectedNoteId}
            loading={sending}
          />
        </div>
      </main>

      <NoteViewer
        noteId={selectedNoteId}
        onClose={() => setSelectedNoteId(null)}
      />
    </div>
  );
}

export function Chat() {
  return (
    <ConversationProvider>
      <ChatContent />
    </ConversationProvider>
  );
}

const styles: Record<string, React.CSSProperties> = {
  container: {
    flex: 1,
    display: 'flex',
    flexDirection: 'column',
    height: '100%',
    overflow: 'hidden',
  },
  titlebar: {
    display: 'flex',
    justifyContent: 'flex-end',
    alignItems: 'center',
    padding: '0 1rem',
    minHeight: '36px',
  },
  titlebarSpacer: {
    flex: 1,
  },
  logoText: {
    fontSize: '1.25rem',
    fontWeight: 700,
    letterSpacing: '0.15em',
    background: 'linear-gradient(135deg, #00d4ff 0%, #7b68ee 50%, #ff6b9d 100%)',
    WebkitBackgroundClip: 'text',
    WebkitTextFillColor: 'transparent',
    backgroundClip: 'text',
  },
  sidebarFooter: {
    flexShrink: 0,
    paddingTop: '1rem',
    borderTop: '1px solid var(--border)',
  },
  settingsButton: {
    backgroundColor: 'transparent',
    border: 'none',
    cursor: 'pointer',
    color: 'var(--text-secondary)',
    padding: '0.5rem',
    borderRadius: '6px',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
  },
  main: {
    flex: 1,
    display: 'flex',
    overflow: 'hidden',
  },
  conversationsSidebar: {
    width: '240px',
    borderRight: '1px solid var(--border)',
    display: 'flex',
    flexDirection: 'column',
    padding: '1rem',
  },
  chatContent: {
    flex: 1,
    display: 'flex',
    flexDirection: 'column',
    minWidth: 0,
  },
  messageArea: {
    flex: 1,
    overflow: 'hidden',
    display: 'flex',
    flexDirection: 'column',
  },
  errorBanner: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    padding: '0.625rem 1rem',
    margin: '0 1rem',
    backgroundColor: 'rgba(255, 59, 48, 0.1)',
    border: '1px solid rgba(255, 59, 48, 0.2)',
    borderRadius: '8px',
    color: '#ff3b30',
    fontSize: '0.875rem',
  },
  errorDismiss: {
    backgroundColor: 'transparent',
    border: 'none',
    color: '#ff3b30',
    cursor: 'pointer',
    padding: '0.25rem',
    display: 'flex',
    alignItems: 'center',
  },
  apiKeyWarning: {
    margin: '0 1rem 0.5rem',
    padding: '1rem',
    backgroundColor: 'rgba(255, 149, 0, 0.1)',
    border: '1px solid rgba(255, 149, 0, 0.3)',
    borderRadius: '8px',
  },
  apiKeyWarningContent: {
    display: 'flex',
    alignItems: 'center',
    gap: '0.75rem',
    color: '#ff9500',
  },
  apiKeyWarningButton: {
    marginLeft: 'auto',
    padding: '0.5rem 1rem',
    backgroundColor: 'var(--accent)',
    border: 'none',
    borderRadius: '6px',
    color: 'white',
    fontSize: '0.85rem',
    fontWeight: 500,
    cursor: 'pointer',
    whiteSpace: 'nowrap',
  },
  inputArea: {
    padding: '0.75rem 1.5rem 1.5rem',
    borderTop: '1px solid var(--border)',
    display: 'flex',
    flexDirection: 'column',
    gap: '0.5rem',
  },
  inputRow: {
    display: 'flex',
    alignItems: 'center',
    gap: '0.5rem',
  },
  resultsSidebar: {
    width: '300px',
    borderLeft: '1px solid var(--border)',
    display: 'flex',
    flexDirection: 'column',
    padding: '1rem',
    overflow: 'hidden',
  },
};

export default Chat;
