import { useState, useCallback } from 'react';
import type { UnifiedCitation } from '../types/trace-api';

interface SourcesProps {
  citations: UnifiedCitation[];
  onNoteClick?: (noteId: string) => void;
  loading?: boolean;
}

export function Sources({ citations, onNoteClick, loading = false }: SourcesProps) {
  const [collapsed, setCollapsed] = useState(false);
  const [expandedNotes, setExpandedNotes] = useState<Set<string>>(new Set());

  const handleWebClick = useCallback((url: string) => {
    window.traceAPI?.shell?.openExternal(url);
  }, []);

  const toggleNoteExpanded = useCallback((id: string) => {
    setExpandedNotes(prev => {
      const next = new Set(prev);
      if (next.has(id)) {
        next.delete(id);
      } else {
        next.add(id);
      }
      return next;
    });
  }, []);

  const webCitations = citations.filter(c => c.type === 'web');
  const noteCitations = citations.filter(c => c.type === 'note');

  if (loading) {
    return (
      <div style={styles.container}>
        <div style={styles.header}>
          <h3 style={styles.title}>Sources</h3>
        </div>
        <div style={styles.loading}>
          <div style={styles.loadingDot} />
          <span>Loading sources...</span>
        </div>
      </div>
    );
  }

  if (citations.length === 0) {
    return (
      <div style={styles.container}>
        <div style={styles.header}>
          <h3 style={styles.title}>Sources</h3>
        </div>
        <div style={styles.empty}>
          <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" style={{ opacity: 0.3 }}>
            <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
            <polyline points="14 2 14 8 20 8" />
          </svg>
          <p>No sources yet</p>
          <span style={styles.emptyHint}>Sources will appear here when you ask a question</span>
        </div>
      </div>
    );
  }

  return (
    <div style={styles.container}>
      {/* Collapsible Header */}
      <button
        style={styles.header}
        onClick={() => setCollapsed(!collapsed)}
        aria-expanded={!collapsed}
      >
        <div style={styles.headerLeft}>
          <svg
            width="12"
            height="12"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            style={{
              ...styles.chevron,
              transform: collapsed ? 'rotate(-90deg)' : 'rotate(0deg)',
            }}
          >
            <polyline points="6 9 12 15 18 9" />
          </svg>
          <h3 style={styles.title}>Sources</h3>
          <span style={styles.count}>{citations.length}</span>
        </div>
      </button>

      {/* Collapsible Content */}
      {!collapsed && (
        <div style={styles.content}>
          {/* Web Sources */}
          {webCitations.length > 0 && (
            <div style={styles.section}>
              <div style={styles.sectionHeader}>
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <circle cx="12" cy="12" r="10" />
                  <line x1="2" y1="12" x2="22" y2="12" />
                  <path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z" />
                </svg>
                <span>Web ({webCitations.length})</span>
              </div>
              <div style={styles.sourcesList}>
                {webCitations.map((cit) => (
                  <a
                    key={cit.id}
                    href="#"
                    onClick={(e) => {
                      e.preventDefault();
                      if (cit.url) handleWebClick(cit.url);
                    }}
                    style={styles.webSource}
                    title={cit.url}
                  >
                    <span style={styles.sourceId}>[{cit.id}]</span>
                    <div style={styles.webSourceContent}>
                      <span style={styles.webTitle}>{cit.title || 'Untitled'}</span>
                      <span style={styles.webDomain}>
                        {cit.url ? new URL(cit.url).hostname.replace('www.', '') : ''}
                      </span>
                      {cit.snippet && (
                        <p style={styles.webSnippet}>{cit.snippet}</p>
                      )}
                    </div>
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" style={styles.externalIcon}>
                      <path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6" />
                      <polyline points="15 3 21 3 21 9" />
                      <line x1="10" y1="14" x2="21" y2="3" />
                    </svg>
                  </a>
                ))}
              </div>
            </div>
          )}

          {/* Note Sources */}
          {noteCitations.length > 0 && (
            <div style={styles.section}>
              <div style={styles.sectionHeader}>
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
                  <polyline points="14 2 14 8 20 8" />
                  <line x1="16" y1="13" x2="8" y2="13" />
                  <line x1="16" y1="17" x2="8" y2="17" />
                </svg>
                <span>Notes ({noteCitations.length})</span>
              </div>
              <div style={styles.sourcesList}>
                {noteCitations.map((cit) => {
                  const isExpanded = expandedNotes.has(cit.id);
                  return (
                    <div key={cit.id} style={styles.noteSource}>
                      <div style={styles.noteHeader}>
                        <span style={styles.sourceId}>[{cit.id}]</span>
                        <button
                          onClick={() => toggleNoteExpanded(cit.id)}
                          style={styles.noteToggle}
                        >
                          <span style={styles.noteType}>
                            {cit.note_type === 'daily' ? '📅' : '⏰'}
                          </span>
                          <span style={styles.noteLabel}>{cit.label}</span>
                          <svg
                            width="12"
                            height="12"
                            viewBox="0 0 24 24"
                            fill="none"
                            stroke="currentColor"
                            strokeWidth="2"
                            style={{
                              ...styles.noteChevron,
                              transform: isExpanded ? 'rotate(180deg)' : 'rotate(0deg)',
                            }}
                          >
                            <polyline points="6 9 12 15 18 9" />
                          </svg>
                        </button>
                      </div>
                      {isExpanded && (
                        <div style={styles.noteContent}>
                          <p style={styles.noteText}>
                            {cit.note_content || 'No preview available'}
                          </p>
                          {cit.note_id && (
                            <button
                              onClick={() => onNoteClick?.(cit.note_id!)}
                              style={styles.viewNoteButton}
                            >
                              View full note
                              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                                <polyline points="9 18 15 12 9 6" />
                              </svg>
                            </button>
                          )}
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

const styles: Record<string, React.CSSProperties> = {
  container: {
    display: 'flex',
    flexDirection: 'column',
    height: '100%',
  },
  header: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    padding: '0.5rem 0',
    backgroundColor: 'transparent',
    border: 'none',
    cursor: 'pointer',
    width: '100%',
    textAlign: 'left',
  },
  headerLeft: {
    display: 'flex',
    alignItems: 'center',
    gap: '0.5rem',
  },
  chevron: {
    transition: 'transform 0.2s ease',
    color: 'var(--text-secondary)',
  },
  title: {
    fontSize: '0.75rem',
    fontWeight: 600,
    color: 'var(--text-secondary)',
    textTransform: 'uppercase',
    letterSpacing: '0.05em',
    margin: 0,
  },
  count: {
    fontSize: '0.7rem',
    fontWeight: 500,
    color: 'var(--text-secondary)',
    backgroundColor: 'var(--bg-secondary)',
    padding: '0.125rem 0.375rem',
    borderRadius: '10px',
  },
  content: {
    flex: 1,
    overflow: 'auto',
    display: 'flex',
    flexDirection: 'column',
    gap: '1rem',
    paddingTop: '0.5rem',
  },
  section: {
    display: 'flex',
    flexDirection: 'column',
    gap: '0.5rem',
  },
  sectionHeader: {
    display: 'flex',
    alignItems: 'center',
    gap: '0.5rem',
    fontSize: '0.75rem',
    fontWeight: 500,
    color: 'var(--text-secondary)',
    paddingBottom: '0.25rem',
    borderBottom: '1px solid var(--border)',
  },
  sourcesList: {
    display: 'flex',
    flexDirection: 'column',
    gap: '0.5rem',
  },
  // Web sources
  webSource: {
    display: 'flex',
    alignItems: 'flex-start',
    gap: '0.5rem',
    padding: '0.625rem',
    backgroundColor: 'var(--bg-secondary)',
    borderRadius: '8px',
    border: '1px solid var(--border)',
    textDecoration: 'none',
    transition: 'border-color 0.2s, background-color 0.2s',
    cursor: 'pointer',
  },
  sourceId: {
    fontSize: '0.75rem',
    fontWeight: 600,
    color: 'var(--accent)',
    flexShrink: 0,
  },
  webSourceContent: {
    flex: 1,
    minWidth: 0,
    display: 'flex',
    flexDirection: 'column',
    gap: '0.125rem',
  },
  webTitle: {
    fontSize: '0.85rem',
    fontWeight: 500,
    color: 'var(--text-primary)',
    overflow: 'hidden',
    textOverflow: 'ellipsis',
    whiteSpace: 'nowrap',
  },
  webDomain: {
    fontSize: '0.7rem',
    color: '#1976d2',
  },
  webSnippet: {
    fontSize: '0.75rem',
    color: 'var(--text-secondary)',
    lineHeight: 1.4,
    margin: '0.25rem 0 0',
    display: '-webkit-box',
    WebkitLineClamp: 2,
    WebkitBoxOrient: 'vertical',
    overflow: 'hidden',
  },
  externalIcon: {
    flexShrink: 0,
    color: 'var(--text-secondary)',
    opacity: 0.5,
  },
  // Note sources
  noteSource: {
    backgroundColor: 'var(--bg-secondary)',
    borderRadius: '8px',
    border: '1px solid var(--border)',
    overflow: 'hidden',
  },
  noteHeader: {
    display: 'flex',
    alignItems: 'center',
    gap: '0.5rem',
    padding: '0.625rem',
  },
  noteToggle: {
    flex: 1,
    display: 'flex',
    alignItems: 'center',
    gap: '0.375rem',
    backgroundColor: 'transparent',
    border: 'none',
    cursor: 'pointer',
    padding: 0,
    textAlign: 'left',
  },
  noteType: {
    fontSize: '0.9rem',
  },
  noteLabel: {
    flex: 1,
    fontSize: '0.85rem',
    fontWeight: 500,
    color: 'var(--text-primary)',
    overflow: 'hidden',
    textOverflow: 'ellipsis',
    whiteSpace: 'nowrap',
  },
  noteChevron: {
    transition: 'transform 0.2s ease',
    color: 'var(--text-secondary)',
    flexShrink: 0,
  },
  noteContent: {
    padding: '0 0.625rem 0.625rem',
    borderTop: '1px solid var(--border)',
    marginTop: '-1px',
  },
  noteText: {
    fontSize: '0.8rem',
    lineHeight: 1.5,
    color: 'var(--text-secondary)',
    margin: '0.625rem 0 0.5rem',
    whiteSpace: 'pre-wrap',
    maxHeight: '120px',
    overflow: 'auto',
  },
  viewNoteButton: {
    display: 'flex',
    alignItems: 'center',
    gap: '0.25rem',
    backgroundColor: 'transparent',
    border: 'none',
    color: 'var(--accent)',
    fontSize: '0.75rem',
    fontWeight: 500,
    cursor: 'pointer',
    padding: '0.25rem 0',
  },
  // Loading & Empty states
  loading: {
    display: 'flex',
    alignItems: 'center',
    gap: '0.75rem',
    padding: '1rem',
    color: 'var(--text-secondary)',
    fontSize: '0.85rem',
  },
  loadingDot: {
    width: '8px',
    height: '8px',
    borderRadius: '50%',
    backgroundColor: 'var(--accent)',
    animation: 'pulse 1.5s ease-in-out infinite',
  },
  empty: {
    flex: 1,
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'center',
    justifyContent: 'center',
    padding: '2rem 1rem',
    textAlign: 'center',
    color: 'var(--text-secondary)',
    fontSize: '0.85rem',
  },
  emptyHint: {
    fontSize: '0.75rem',
    opacity: 0.7,
    marginTop: '0.25rem',
  },
};

export default Sources;
