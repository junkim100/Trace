import { useState, useEffect, useCallback, useRef, Fragment } from 'react';
import type { ChatResponse, UnifiedCitation } from '../types/trace-api';

interface AnswerProps {
  response: ChatResponse | null;
  loading?: boolean;
  error?: string | null;
  onCitationClick?: (noteId: string) => void;
  onRetry?: () => void;
  onSuggestionClick?: (question: string) => void;
  onFollowUpAnswer?: (question: string, answer: string) => void;
  followUpInputValue?: string;
  onFollowUpInputChange?: (value: string) => void;
}

// Citation popup component for note citations
interface CitationPopupProps {
  citation: UnifiedCitation;
  position: { x: number; y: number };
  onClose: () => void;
}

function CitationPopup({ citation, position, onClose }: CitationPopupProps) {
  const popupRef = useRef<HTMLDivElement>(null);

  // Position popup to stay within viewport
  useEffect(() => {
    if (popupRef.current) {
      const popup = popupRef.current;
      const rect = popup.getBoundingClientRect();
      const viewportWidth = window.innerWidth;
      const viewportHeight = window.innerHeight;

      // Adjust if popup goes off right edge
      if (rect.right > viewportWidth - 16) {
        popup.style.left = `${viewportWidth - rect.width - 16}px`;
      }

      // Adjust if popup goes off bottom edge
      if (rect.bottom > viewportHeight - 16) {
        popup.style.top = `${viewportHeight - rect.height - 16}px`;
      }
    }
  }, [position]);

  return (
    <div
      ref={popupRef}
      style={{
        ...styles.citationPopup,
        left: position.x + 10,
        top: position.y + 10,
      }}
      onMouseLeave={onClose}
    >
      <div style={styles.popupHeader}>
        <span style={styles.popupType}>
          {citation.note_type === 'daily' ? '📅 Daily' : '⏰ Hourly'} note
        </span>
        <span style={styles.popupTimestamp}>{citation.label}</span>
      </div>
      <div style={styles.popupContent}>
        {citation.note_content || 'No preview available'}
      </div>
    </div>
  );
}

// Inline citation marker component
interface CitationMarkerProps {
  citation: UnifiedCitation;
  onNoteHover: (e: React.MouseEvent, citation: UnifiedCitation) => void;
  onNoteLeave: () => void;
  onWebClick: (url: string) => void;
  onNoteClick: (noteId: string) => void;
}

function CitationMarker({ citation, onNoteHover, onNoteLeave, onWebClick, onNoteClick }: CitationMarkerProps) {
  const isWeb = citation.type === 'web';

  const handleClick = () => {
    if (isWeb && citation.url) {
      onWebClick(citation.url);
    } else if (!isWeb && citation.note_id) {
      onNoteClick(citation.note_id);
    }
  };

  return (
    <button
      style={{
        ...styles.inlineCitationMarker,
        ...(isWeb ? styles.inlineCitationWeb : styles.inlineCitationNote),
      }}
      onMouseEnter={(e) => !isWeb && onNoteHover(e, citation)}
      onMouseLeave={() => !isWeb && onNoteLeave()}
      onClick={handleClick}
      title={isWeb ? `Open: ${citation.title}` : `View note: ${citation.label}`}
    >
      [{citation.id}]
    </button>
  );
}

// Parse answer text and replace [N] with citation markers
function renderAnswerWithCitations(
  answer: string,
  citations: UnifiedCitation[],
  onNoteHover: (e: React.MouseEvent, citation: UnifiedCitation) => void,
  onNoteLeave: () => void,
  onWebClick: (url: string) => void,
  onNoteClick: (noteId: string) => void
): React.ReactNode {
  // If no unified citations, just return the text
  if (!citations || citations.length === 0) {
    return answer;
  }

  // Split by citation markers [N]
  const parts = answer.split(/(\[\d+\])/g);

  return parts.map((part, index) => {
    const match = part.match(/\[(\d+)\]/);
    if (match) {
      const citId = match[1];
      const citation = citations.find(c => c.id === citId);
      if (citation) {
        return (
          <CitationMarker
            key={`cit-${index}`}
            citation={citation}
            onNoteHover={onNoteHover}
            onNoteLeave={onNoteLeave}
            onWebClick={onWebClick}
            onNoteClick={onNoteClick}
          />
        );
      }
      // Return the marker as-is if no matching citation
      return <span key={`text-${index}`}>{part}</span>;
    }
    return <Fragment key={`text-${index}`}>{part}</Fragment>;
  });
}

// Citation reference list at the bottom
function CitationReferenceList({
  citations,
  onWebClick,
  onNoteClick,
}: {
  citations: UnifiedCitation[];
  onWebClick: (url: string) => void;
  onNoteClick: (noteId: string) => void;
}) {
  if (!citations || citations.length === 0) return null;

  return (
    <div style={styles.citationReferenceList}>
      <span style={styles.citationsLabel}>Sources</span>
      <div style={styles.referenceItems}>
        {citations.map((cit) => (
          <div
            key={cit.id}
            style={{
              ...styles.referenceItem,
              ...(cit.type === 'web' ? styles.referenceItemWeb : styles.referenceItemNote),
            }}
          >
            <span style={styles.referenceId}>[{cit.id}]</span>
            {cit.type === 'web' ? (
              <a
                href="#"
                onClick={(e) => {
                  e.preventDefault();
                  if (cit.url) onWebClick(cit.url);
                }}
                style={styles.referenceLink}
                title={cit.url}
              >
                {cit.title || cit.url}
              </a>
            ) : (
              <button
                onClick={() => cit.note_id && onNoteClick(cit.note_id)}
                style={styles.referenceNoteButton}
              >
                {cit.note_type === 'daily' ? '📅' : '⏰'} {cit.label}
              </button>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}

// Example questions for the placeholder
const EXAMPLE_QUESTIONS = [
  "What did I work on today?",
  "What were my most used apps this week?",
  "Tell me about Python",
];

// Loading message progression for better UX
const LOADING_MESSAGES = [
  'Searching your notes...',
  'Analyzing activity data...',
  'Building context...',
  'Generating response...',
];

// Categorize errors for better user feedback
function categorizeError(error: string): { type: 'network' | 'api' | 'timeout' | 'unknown'; message: string; suggestion: string } {
  const lowerError = error.toLowerCase();

  if (lowerError.includes('network') || lowerError.includes('fetch') || lowerError.includes('connection')) {
    return {
      type: 'network',
      message: 'Unable to connect',
      suggestion: 'Check your internet connection and try again.',
    };
  }

  if (lowerError.includes('timeout') || lowerError.includes('timed out')) {
    return {
      type: 'timeout',
      message: 'Request timed out',
      suggestion: 'The request took too long. Try a simpler query or try again.',
    };
  }

  if (lowerError.includes('rate limit') || lowerError.includes('429')) {
    return {
      type: 'api',
      message: 'Too many requests',
      suggestion: 'Please wait a moment before trying again.',
    };
  }

  if (lowerError.includes('api') || lowerError.includes('openai') || lowerError.includes('500')) {
    return {
      type: 'api',
      message: 'Service temporarily unavailable',
      suggestion: 'The AI service may be experiencing issues. Please try again.',
    };
  }

  return {
    type: 'unknown',
    message: error,
    suggestion: 'Try again or rephrase your question.',
  };
}

export function Answer({ response, loading = false, error = null, onCitationClick, onRetry, onSuggestionClick, onFollowUpAnswer, followUpInputValue = '', onFollowUpInputChange }: AnswerProps) {
  const [loadingMessageIndex, setLoadingMessageIndex] = useState(0);
  const [loadingDots, setLoadingDots] = useState('');
  const [popupCitation, setPopupCitation] = useState<UnifiedCitation | null>(null);
  const [popupPosition, setPopupPosition] = useState({ x: 0, y: 0 });

  // Handlers for citation interactions
  const handleNoteHover = useCallback((e: React.MouseEvent, citation: UnifiedCitation) => {
    setPopupCitation(citation);
    setPopupPosition({ x: e.clientX, y: e.clientY });
  }, []);

  const handleNoteLeave = useCallback(() => {
    setPopupCitation(null);
  }, []);

  const handleWebClick = useCallback((url: string) => {
    // Open URL in external browser
    window.traceAPI?.shell?.openExternal(url);
  }, []);

  const handleNoteClick = useCallback((noteId: string) => {
    onCitationClick?.(noteId);
  }, [onCitationClick]);

  // Animate loading message progression
  useEffect(() => {
    if (!loading) {
      setLoadingMessageIndex(0);
      setLoadingDots('');
      return;
    }

    // Progress through loading messages
    const messageInterval = setInterval(() => {
      setLoadingMessageIndex(prev =>
        prev < LOADING_MESSAGES.length - 1 ? prev + 1 : prev
      );
    }, 2000);

    // Animate dots
    const dotsInterval = setInterval(() => {
      setLoadingDots(prev => prev.length >= 3 ? '' : prev + '.');
    }, 400);

    return () => {
      clearInterval(messageInterval);
      clearInterval(dotsInterval);
    };
  }, [loading]);

  if (loading) {
    return (
      <div style={styles.container}>
        <div style={styles.loading}>
          <div style={styles.spinnerContainer}>
            <div style={styles.spinner} />
            <div style={styles.spinnerGlow} />
          </div>
          <div style={styles.loadingText}>
            <span style={styles.loadingMessage}>
              {LOADING_MESSAGES[loadingMessageIndex]}{loadingDots}
            </span>
            <div style={styles.loadingProgress}>
              {LOADING_MESSAGES.map((_, idx) => (
                <div
                  key={idx}
                  style={{
                    ...styles.progressDot,
                    backgroundColor: idx <= loadingMessageIndex
                      ? 'var(--accent)'
                      : 'var(--border)',
                  }}
                />
              ))}
            </div>
          </div>
        </div>
      </div>
    );
  }

  if (error) {
    const errorInfo = categorizeError(error);

    return (
      <div style={styles.container}>
        <div style={styles.error}>
          <div style={styles.errorHeader}>
            <div style={styles.errorIcon}>
              <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <circle cx="12" cy="12" r="10" />
                <path d="M12 8v4" />
                <path d="M12 16h.01" />
              </svg>
            </div>
            <div style={styles.errorContent}>
              <span style={styles.errorTitle}>{errorInfo.message}</span>
              <span style={styles.errorSuggestion}>{errorInfo.suggestion}</span>
            </div>
          </div>

          {onRetry && (
            <button onClick={onRetry} style={styles.retryButton}>
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M1 4v6h6" />
                <path d="M3.51 15a9 9 0 1 0 2.13-9.36L1 10" />
              </svg>
              Try Again
            </button>
          )}
        </div>
      </div>
    );
  }

  if (!response) {
    return (
      <div style={styles.container}>
        <div style={styles.placeholder}>
          <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" style={{ opacity: 0.3 }}>
            <circle cx="11" cy="11" r="8" />
            <path d="M21 21l-4.35-4.35" />
          </svg>
          <p style={styles.placeholderText}>Ask a question about your activity</p>
          <div style={styles.suggestions}>
            <span style={styles.suggestionLabel}>Try asking:</span>
            {EXAMPLE_QUESTIONS.map((question, idx) => (
              <button
                key={idx}
                onClick={() => onSuggestionClick?.(question)}
                style={styles.suggestionButton}
              >
                {question}
              </button>
            ))}
          </div>
        </div>
      </div>
    );
  }

  // Check if we have unified citations (v0.8.0 web search integration)
  const hasUnifiedCitations = response.unified_citations && response.unified_citations.length > 0;

  return (
    <div style={styles.container}>
      <div style={styles.answer}>
        {hasUnifiedCitations ? (
          // v0.8.0: Render answer with inline [N] citation markers
          <div style={styles.answerText}>
            {renderAnswerWithCitations(
              response.answer,
              response.unified_citations!,
              handleNoteHover,
              handleNoteLeave,
              handleWebClick,
              handleNoteClick
            )}
          </div>
        ) : (
          // Legacy: Plain text answer
          <p style={styles.answerText}>{response.answer}</p>
        )}

        {/* v0.8.0: Citation reference list (Perplexity-style) */}
        {hasUnifiedCitations && (
          <CitationReferenceList
            citations={response.unified_citations!}
            onWebClick={handleWebClick}
            onNoteClick={handleNoteClick}
          />
        )}

        {/* Legacy citations (backwards compatibility) */}
        {!hasUnifiedCitations && response.citations.length > 0 && (
          <div style={styles.citations}>
            <span style={styles.citationsLabel}>Sources:</span>
            <div style={styles.citationsList}>
              {response.citations.map((citation, idx) => {
                // Format the timestamp as a readable label
                const formatCitationLabel = (timestamp: string) => {
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
                    return `Note ${idx + 1}`;
                  }
                };
                return (
                  <button
                    key={idx}
                    onClick={() => onCitationClick?.(citation.note_id)}
                    style={styles.citationButton}
                    title={citation.quote}
                  >
                    {formatCitationLabel(citation.timestamp)}
                  </button>
                );
              })}
            </div>
          </div>
        )}
      </div>

      {/* Citation popup for note previews */}
      {popupCitation && (
        <CitationPopup
          citation={popupCitation}
          position={popupPosition}
          onClose={handleNoteLeave}
        />
      )}

      <div style={styles.meta}>
        {response.time_filter && (
          <span style={styles.metaItem}>
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <circle cx="12" cy="12" r="10" />
              <path d="M12 6v6l4 2" />
            </svg>
            {response.time_filter.description}
          </span>
        )}
        <span style={styles.metaItem}>
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14" />
            <polyline points="22 4 12 14.01 9 11.01" />
          </svg>
          {Math.round((response.confidence ?? 0) * 100)}% confident
        </span>
        <span style={styles.metaItem}>
          {(response.processing_time_ms ?? 0).toFixed(0)}ms
        </span>
      </div>

      {response.aggregates.length > 0 && (
        <div style={styles.aggregates}>
          <h4 style={styles.aggregatesTitle}>Top Activity</h4>
          <div style={styles.aggregatesList}>
            {response.aggregates.slice(0, 5).map((agg, idx) => (
              <div key={idx} style={styles.aggregateItem}>
                <span style={styles.aggregateKey}>{agg.key}</span>
                <span style={styles.aggregateValue}>
                  {formatValue(agg.value, agg.key_type)}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}

      {response.follow_up && onFollowUpAnswer && (
        <div style={styles.followUp}>
          <div style={styles.followUpHeader}>
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <circle cx="12" cy="12" r="10" />
              <path d="M9.09 9a3 3 0 0 1 5.83 1c0 2-3 3-3 3" />
              <line x1="12" y1="17" x2="12.01" y2="17" />
            </svg>
            <span style={styles.followUpLabel}>Getting to know you</span>
          </div>
          <p style={styles.followUpQuestion}>{response.follow_up.question}</p>
          <div style={styles.followUpInputContainer}>
            <input
              type="text"
              value={followUpInputValue}
              onChange={(e) => onFollowUpInputChange?.(e.target.value)}
              onKeyPress={(e) => {
                if (e.key === 'Enter' && followUpInputValue.trim()) {
                  onFollowUpAnswer(response.follow_up!.question, followUpInputValue.trim());
                }
              }}
              placeholder="Your answer..."
              style={styles.followUpInput}
            />
            <button
              onClick={() => {
                if (followUpInputValue.trim()) {
                  onFollowUpAnswer(response.follow_up!.question, followUpInputValue.trim());
                }
              }}
              disabled={!followUpInputValue.trim()}
              style={{
                ...styles.followUpButton,
                ...(!followUpInputValue.trim() ? styles.followUpButtonDisabled : {}),
              }}
            >
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <line x1="22" y1="2" x2="11" y2="13" />
                <polygon points="22 2 15 22 11 13 2 9 22 2" />
              </svg>
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

function formatValue(value: number, _keyType: string): string {
  // Value is typically in minutes
  if (value >= 60) {
    const hours = Math.floor(value / 60);
    const mins = Math.round(value % 60);
    return mins > 0 ? `${hours}h ${mins}m` : `${hours}h`;
  }
  return `${Math.round(value)}m`;
}

const styles: Record<string, React.CSSProperties> = {
  container: {
    flex: 1,
    display: 'flex',
    flexDirection: 'column',
    minHeight: 0,
  },
  loading: {
    display: 'flex',
    alignItems: 'center',
    gap: '1rem',
    padding: '1.5rem',
    color: 'var(--text-secondary)',
  },
  spinnerContainer: {
    position: 'relative',
    width: '32px',
    height: '32px',
  },
  spinner: {
    width: '32px',
    height: '32px',
    border: '3px solid var(--border)',
    borderTopColor: 'var(--accent)',
    borderRadius: '50%',
    animation: 'spin 1s linear infinite',
  },
  spinnerGlow: {
    position: 'absolute',
    top: '-2px',
    left: '-2px',
    width: '36px',
    height: '36px',
    borderRadius: '50%',
    background: 'radial-gradient(circle, rgba(0, 122, 255, 0.2) 0%, transparent 70%)',
    animation: 'pulse 2s ease-in-out infinite',
  },
  loadingText: {
    display: 'flex',
    flexDirection: 'column',
    gap: '0.5rem',
  },
  loadingMessage: {
    fontSize: '0.95rem',
    color: 'var(--text-primary)',
    minWidth: '180px',
  },
  loadingProgress: {
    display: 'flex',
    gap: '0.375rem',
  },
  progressDot: {
    width: '6px',
    height: '6px',
    borderRadius: '50%',
    transition: 'background-color 0.3s ease',
  },
  error: {
    display: 'flex',
    flexDirection: 'column',
    gap: '1rem',
    padding: '1.25rem',
    backgroundColor: 'rgba(255, 59, 48, 0.08)',
    border: '1px solid rgba(255, 59, 48, 0.2)',
    borderRadius: '12px',
  },
  errorHeader: {
    display: 'flex',
    alignItems: 'flex-start',
    gap: '0.875rem',
  },
  errorIcon: {
    flexShrink: 0,
    color: '#ff3b30',
    marginTop: '2px',
  },
  errorContent: {
    display: 'flex',
    flexDirection: 'column',
    gap: '0.375rem',
  },
  errorTitle: {
    fontSize: '0.95rem',
    fontWeight: 500,
    color: '#ff3b30',
  },
  errorSuggestion: {
    fontSize: '0.85rem',
    color: 'var(--text-secondary)',
  },
  retryButton: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    gap: '0.5rem',
    padding: '0.625rem 1rem',
    backgroundColor: 'rgba(255, 59, 48, 0.12)',
    border: '1px solid rgba(255, 59, 48, 0.25)',
    borderRadius: '8px',
    fontSize: '0.875rem',
    fontWeight: 500,
    color: '#ff3b30',
    cursor: 'pointer',
    transition: 'all 0.2s ease',
    alignSelf: 'flex-start',
  },
  placeholder: {
    flex: 1,
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'center',
    justifyContent: 'center',
    padding: '2rem',
    textAlign: 'center',
  },
  placeholderText: {
    fontSize: '1.1rem',
    color: 'var(--text-secondary)',
    marginTop: '1rem',
  },
  suggestions: {
    marginTop: '1.5rem',
    display: 'flex',
    flexDirection: 'column',
    gap: '0.5rem',
    alignItems: 'center',
  },
  suggestionLabel: {
    fontSize: '0.85rem',
    color: 'var(--text-secondary)',
    marginBottom: '0.5rem',
  },
  suggestionButton: {
    backgroundColor: 'rgba(0, 122, 255, 0.1)',
    border: '1px solid rgba(0, 122, 255, 0.25)',
    borderRadius: '8px',
    padding: '0.625rem 1rem',
    fontSize: '0.85rem',
    color: 'var(--accent)',
    cursor: 'pointer',
    transition: 'all 0.2s ease',
    textAlign: 'left' as const,
  },
  answer: {
    padding: '1.5rem',
    backgroundColor: 'var(--bg-secondary)',
    borderRadius: '12px',
    border: '1px solid var(--border)',
    marginBottom: '1rem',
  },
  answerText: {
    fontSize: '1rem',
    lineHeight: 1.6,
    color: 'var(--text-primary)',
    whiteSpace: 'pre-wrap',
  },
  citations: {
    marginTop: '1rem',
    paddingTop: '1rem',
    borderTop: '1px solid var(--border)',
  },
  citationsLabel: {
    fontSize: '0.75rem',
    color: 'var(--text-secondary)',
    textTransform: 'uppercase',
    letterSpacing: '0.05em',
  },
  citationsList: {
    display: 'flex',
    flexWrap: 'wrap',
    gap: '0.5rem',
    marginTop: '0.5rem',
  },
  citationButton: {
    backgroundColor: 'rgba(0, 122, 255, 0.1)',
    border: '1px solid rgba(0, 122, 255, 0.2)',
    borderRadius: '4px',
    padding: '0.25rem 0.5rem',
    fontSize: '0.75rem',
    color: 'var(--accent)',
    cursor: 'pointer',
    transition: 'background-color 0.2s',
  },
  meta: {
    display: 'flex',
    flexWrap: 'wrap',
    gap: '1rem',
    marginBottom: '1rem',
  },
  metaItem: {
    display: 'flex',
    alignItems: 'center',
    gap: '0.375rem',
    fontSize: '0.8rem',
    color: 'var(--text-secondary)',
  },
  aggregates: {
    backgroundColor: 'var(--bg-secondary)',
    borderRadius: '8px',
    border: '1px solid var(--border)',
    padding: '1rem',
  },
  aggregatesTitle: {
    fontSize: '0.75rem',
    fontWeight: 600,
    color: 'var(--text-secondary)',
    textTransform: 'uppercase',
    letterSpacing: '0.05em',
    marginBottom: '0.75rem',
  },
  aggregatesList: {
    display: 'flex',
    flexDirection: 'column',
    gap: '0.5rem',
  },
  aggregateItem: {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
    padding: '0.375rem 0',
  },
  aggregateKey: {
    fontSize: '0.85rem',
    color: 'var(--text-primary)',
  },
  aggregateValue: {
    fontSize: '0.85rem',
    color: 'var(--accent)',
    fontWeight: 500,
  },
  followUp: {
    marginTop: '1rem',
    padding: '1rem',
    backgroundColor: 'rgba(0, 122, 255, 0.08)',
    border: '1px solid rgba(0, 122, 255, 0.2)',
    borderRadius: '12px',
  },
  followUpHeader: {
    display: 'flex',
    alignItems: 'center',
    gap: '0.5rem',
    marginBottom: '0.75rem',
    color: 'var(--accent)',
  },
  followUpLabel: {
    fontSize: '0.8rem',
    fontWeight: 600,
    textTransform: 'uppercase' as const,
    letterSpacing: '0.05em',
  },
  followUpQuestion: {
    fontSize: '0.95rem',
    color: 'var(--text-primary)',
    marginBottom: '0.75rem',
    lineHeight: 1.5,
  },
  followUpInputContainer: {
    display: 'flex',
    gap: '0.5rem',
  },
  followUpInput: {
    flex: 1,
    backgroundColor: 'var(--bg-primary)',
    border: '1px solid var(--border)',
    borderRadius: '8px',
    padding: '0.625rem 0.875rem',
    fontSize: '0.9rem',
    color: 'var(--text-primary)',
    outline: 'none',
  },
  followUpButton: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    width: '40px',
    height: '40px',
    backgroundColor: 'var(--accent)',
    border: 'none',
    borderRadius: '8px',
    color: 'white',
    cursor: 'pointer',
    transition: 'opacity 0.2s',
  },
  followUpButtonDisabled: {
    opacity: 0.5,
    cursor: 'not-allowed',
  },
  // v0.8.0: Inline citation markers
  inlineCitationMarker: {
    display: 'inline',
    padding: '0 3px',
    margin: '0 1px',
    fontSize: '0.8em',
    fontWeight: 600,
    border: 'none',
    borderRadius: '4px',
    cursor: 'pointer',
    verticalAlign: 'super',
    lineHeight: 1,
    transition: 'opacity 0.2s',
  },
  inlineCitationWeb: {
    backgroundColor: '#e3f2fd',
    color: '#1976d2',
  },
  inlineCitationNote: {
    backgroundColor: '#f3e5f5',
    color: '#7b1fa2',
  },
  // Citation popup
  citationPopup: {
    position: 'fixed' as const,
    backgroundColor: 'var(--bg-primary)',
    border: '1px solid var(--border)',
    borderRadius: '10px',
    boxShadow: '0 4px 16px rgba(0,0,0,0.15)',
    padding: '12px',
    zIndex: 1000,
    maxWidth: '380px',
    maxHeight: '280px',
    overflow: 'hidden',
  },
  popupHeader: {
    display: 'flex',
    justifyContent: 'space-between',
    marginBottom: '8px',
    fontSize: '0.8em',
    color: 'var(--text-secondary)',
  },
  popupType: {
    fontWeight: 500,
  },
  popupTimestamp: {
    color: 'var(--accent)',
  },
  popupContent: {
    fontSize: '0.85em',
    lineHeight: 1.5,
    color: 'var(--text-primary)',
    overflowY: 'auto' as const,
    maxHeight: '200px',
  },
  // Citation reference list
  citationReferenceList: {
    marginTop: '1rem',
    paddingTop: '1rem',
    borderTop: '1px solid var(--border)',
  },
  referenceItems: {
    display: 'flex',
    flexDirection: 'column' as const,
    gap: '6px',
    marginTop: '8px',
  },
  referenceItem: {
    display: 'flex',
    alignItems: 'center',
    gap: '8px',
    fontSize: '0.85em',
    padding: '4px 0',
  },
  referenceItemWeb: {},
  referenceItemNote: {},
  referenceId: {
    fontWeight: 600,
    color: 'var(--text-secondary)',
    minWidth: '24px',
  },
  referenceLink: {
    color: '#1976d2',
    textDecoration: 'none',
    overflow: 'hidden',
    textOverflow: 'ellipsis',
    whiteSpace: 'nowrap' as const,
    maxWidth: '300px',
  },
  referenceNoteButton: {
    background: 'none',
    border: 'none',
    color: '#7b1fa2',
    cursor: 'pointer',
    padding: 0,
    fontSize: 'inherit',
    textAlign: 'left' as const,
  },
};

export default Answer;
