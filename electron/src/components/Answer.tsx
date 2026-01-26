import { useState, useEffect } from 'react';
import type { ChatResponse } from '../types/trace-api';

interface AnswerProps {
  response: ChatResponse | null;
  loading?: boolean;
  error?: string | null;
  onCitationClick?: (noteId: string) => void;
  onRetry?: () => void;
  onSuggestionClick?: (question: string) => void;
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

export function Answer({ response, loading = false, error = null, onCitationClick, onRetry, onSuggestionClick }: AnswerProps) {
  const [loadingMessageIndex, setLoadingMessageIndex] = useState(0);
  const [loadingDots, setLoadingDots] = useState('');

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

  return (
    <div style={styles.container}>
      <div style={styles.answer}>
        <p style={styles.answerText}>{response.answer}</p>

        {response.citations.length > 0 && (
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
};

export default Answer;
