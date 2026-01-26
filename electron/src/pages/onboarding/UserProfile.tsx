import React, { useState, useEffect, useRef } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import { OnboardingLayout } from './OnboardingLayout';

const styles: Record<string, React.CSSProperties> = {
  container: {
    display: 'flex',
    flexDirection: 'column',
    height: '100%',
    maxHeight: 'calc(100vh - 180px)',
  },
  title: {
    fontSize: 28,
    fontWeight: 700,
    marginBottom: 8,
    background: 'linear-gradient(135deg, #007aff, #00d4ff)',
    WebkitBackgroundClip: 'text',
    WebkitTextFillColor: 'transparent',
    textAlign: 'center',
  },
  subtitle: {
    fontSize: 16,
    color: 'var(--text-secondary)',
    marginBottom: 24,
    textAlign: 'center',
    lineHeight: 1.6,
  },
  chatContainer: {
    flex: 1,
    backgroundColor: 'var(--bg-secondary)',
    borderRadius: 16,
    border: '1px solid var(--border)',
    display: 'flex',
    flexDirection: 'column',
    overflow: 'hidden',
    minHeight: 300,
    maxHeight: 400,
  },
  messagesContainer: {
    flex: 1,
    overflowY: 'auto',
    padding: 20,
    display: 'flex',
    flexDirection: 'column',
    gap: 16,
  },
  messageRow: {
    display: 'flex',
    alignItems: 'flex-start',
    gap: 12,
  },
  messageRowUser: {
    flexDirection: 'row-reverse',
  },
  avatar: {
    width: 36,
    height: 36,
    borderRadius: 12,
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    flexShrink: 0,
    fontSize: 14,
    fontWeight: 600,
  },
  avatarAssistant: {
    background: 'linear-gradient(135deg, #007aff, #00d4ff)',
    color: 'white',
  },
  avatarUser: {
    backgroundColor: 'rgba(255, 255, 255, 0.1)',
    color: 'var(--text-primary)',
  },
  messageBubble: {
    maxWidth: '80%',
    padding: '12px 16px',
    borderRadius: 16,
    fontSize: 15,
    lineHeight: 1.5,
  },
  messageBubbleAssistant: {
    backgroundColor: 'rgba(0, 122, 255, 0.1)',
    color: 'var(--text-primary)',
    borderTopLeftRadius: 4,
  },
  messageBubbleUser: {
    backgroundColor: 'var(--accent)',
    color: 'white',
    borderTopRightRadius: 4,
  },
  typingIndicator: {
    display: 'flex',
    gap: 4,
    padding: '12px 16px',
    backgroundColor: 'rgba(0, 122, 255, 0.1)',
    borderRadius: 16,
    borderTopLeftRadius: 4,
    maxWidth: 80,
  },
  typingDot: {
    width: 8,
    height: 8,
    borderRadius: '50%',
    backgroundColor: 'var(--text-secondary)',
    animation: 'typingBounce 1.4s infinite ease-in-out both',
  },
  inputContainer: {
    padding: 16,
    borderTop: '1px solid var(--border)',
    display: 'flex',
    gap: 12,
    alignItems: 'flex-end',
  },
  input: {
    flex: 1,
    padding: '12px 16px',
    fontSize: 15,
    backgroundColor: 'rgba(0, 0, 0, 0.2)',
    border: '1px solid var(--border)',
    borderRadius: 12,
    color: 'var(--text-primary)',
    outline: 'none',
    resize: 'none',
    fontFamily: 'inherit',
    minHeight: 44,
    maxHeight: 120,
    transition: 'border-color 0.2s ease',
  },
  sendButton: {
    width: 44,
    height: 44,
    borderRadius: 12,
    border: 'none',
    backgroundColor: 'var(--accent)',
    color: 'white',
    cursor: 'pointer',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    transition: 'all 0.2s ease',
    flexShrink: 0,
  },
  sendButtonDisabled: {
    opacity: 0.5,
    cursor: 'not-allowed',
  },
  phaseIndicator: {
    display: 'flex',
    justifyContent: 'center',
    gap: 8,
    marginBottom: 24,
  },
  phaseDot: {
    width: 8,
    height: 8,
    borderRadius: '50%',
    backgroundColor: 'var(--border)',
    transition: 'all 0.3s ease',
  },
  phaseDotActive: {
    backgroundColor: 'var(--accent)',
    transform: 'scale(1.2)',
  },
  phaseDotCompleted: {
    backgroundColor: '#34c759',
  },
  buttonContainer: {
    display: 'flex',
    gap: 12,
    justifyContent: 'center',
    marginTop: 24,
  },
  skipButton: {
    padding: '14px 32px',
    fontSize: 16,
    fontWeight: 500,
    backgroundColor: 'transparent',
    color: 'var(--text-secondary)',
    border: '1px solid var(--border)',
    borderRadius: 10,
    cursor: 'pointer',
    transition: 'all 0.2s ease',
  },
  continueButton: {
    padding: '14px 48px',
    fontSize: 16,
    fontWeight: 600,
    backgroundColor: 'var(--accent)',
    color: 'white',
    border: 'none',
    borderRadius: 10,
    cursor: 'pointer',
    transition: 'all 0.2s ease',
    boxShadow: '0 4px 12px rgba(0, 122, 255, 0.3)',
  },
  continueButtonDisabled: {
    opacity: 0.5,
    cursor: 'not-allowed',
  },
  memorySummary: {
    backgroundColor: 'rgba(0, 122, 255, 0.05)',
    border: '1px solid rgba(0, 122, 255, 0.2)',
    borderRadius: 12,
    padding: 16,
    marginBottom: 24,
    fontSize: 14,
    color: 'var(--text-secondary)',
    lineHeight: 1.6,
  },
  memorySummaryTitle: {
    fontSize: 14,
    fontWeight: 600,
    color: 'var(--text-primary)',
    marginBottom: 8,
  },
};

// Add keyframes for typing animation
const typingAnimationStyle = `
  @keyframes typingBounce {
    0%, 80%, 100% { transform: translateY(0); }
    40% { transform: translateY(-6px); }
  }
`;

interface Message {
  role: 'assistant' | 'user';
  content: string;
}

type OnboardingMode = 'initial' | 'update' | 'restart';

const PHASES = ['greeting', 'name', 'occupation', 'interests', 'open_ended', 'confirming', 'complete'];

const getPhaseIndex = (phase: string): number => {
  const idx = PHASES.indexOf(phase);
  return idx >= 0 ? idx : 0;
};

export const UserProfile: React.FC = () => {
  const navigate = useNavigate();
  const location = useLocation();
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  // Get mode from location state or default to 'initial'
  const mode: OnboardingMode = (location.state as { mode?: OnboardingMode })?.mode || 'initial';

  const [messages, setMessages] = useState<Message[]>([]);
  const [inputValue, setInputValue] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [phase, setPhase] = useState('greeting');
  const [extracted, setExtracted] = useState<Record<string, unknown>>({});
  const [isComplete, setIsComplete] = useState(false);
  const [isReadyToContinue, setIsReadyToContinue] = useState(false);
  const [memorySummary, setMemorySummary] = useState<string | null>(null);
  const [hasApiKey, setHasApiKey] = useState(false);
  const [isFinalizing, setIsFinalizing] = useState(false);

  // Scroll to bottom when messages change
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, isLoading]);

  // Check API key status
  useEffect(() => {
    const checkApiKey = async () => {
      try {
        const settings = await window.traceAPI.settings.get();
        setHasApiKey(settings.has_api_key);
      } catch {
        // Ignore errors
      }
    };
    checkApiKey();
  }, []);

  // Initialize conversation
  useEffect(() => {
    const initialize = async () => {
      setIsLoading(true);
      try {
        // For update mode, get memory summary first
        if (mode === 'update') {
          const summaryResult = await window.traceAPI.onboarding.getSummary();
          if (summaryResult.success && summaryResult.summary) {
            setMemorySummary(summaryResult.summary);
          }
        }

        // For restart mode, clear memory first
        if (mode === 'restart') {
          await window.traceAPI.onboarding.clear();
        }

        // Start the onboarding conversation
        const result = await window.traceAPI.onboarding.start(mode);
        if (result.success) {
          setMessages([{ role: 'assistant', content: result.message }]);
          setPhase(result.phase);
          setExtracted(result.extracted || {});
        }
      } catch (err) {
        console.error('Failed to initialize onboarding:', err);
        setMessages([{
          role: 'assistant',
          content: "Hi! I'm Trace. Let me get to know you better so I can personalize your experience. What should I call you?"
        }]);
      } finally {
        setIsLoading(false);
      }
    };

    initialize();
  }, [mode]);

  const handleSend = async () => {
    const message = inputValue.trim();
    if (!message || isLoading) return;

    // Add user message
    const newMessages: Message[] = [...messages, { role: 'user', content: message }];
    setMessages(newMessages);
    setInputValue('');
    setIsLoading(true);

    try {
      // Convert messages to history format
      const history = newMessages.map(m => ({
        role: m.role,
        content: m.content,
      }));

      const result = await window.traceAPI.onboarding.chat({
        phase,
        message,
        history,
        extracted,
        mode,
      });

      if (result.success) {
        setMessages([...newMessages, { role: 'assistant', content: result.response }]);
        setPhase(result.phase);
        setExtracted(result.extracted || {});
        setIsComplete(result.completion_detected || false);
        setIsReadyToContinue(result.is_ready_to_continue || false);
      }
    } catch (err) {
      console.error('Failed to process message:', err);
      setMessages([...newMessages, {
        role: 'assistant',
        content: "I'm sorry, I had trouble processing that. Could you try again?"
      }]);
    } finally {
      setIsLoading(false);
      inputRef.current?.focus();
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const handleSkip = () => {
    navigateNext();
  };

  const handleContinue = async () => {
    if (isFinalizing) return;

    setIsFinalizing(true);
    try {
      // Finalize and save to memory
      const history = messages.map(m => ({
        role: m.role,
        content: m.content,
      }));

      await window.traceAPI.onboarding.finalize({
        history,
        extracted,
      });

      navigateNext();
    } catch (err) {
      console.error('Failed to finalize onboarding:', err);
      // Navigate anyway - data is saved incrementally
      navigateNext();
    } finally {
      setIsFinalizing(false);
    }
  };

  const navigateNext = () => {
    if (mode === 'update' || mode === 'restart') {
      // Return to settings for update/restart modes
      navigate('/settings');
    } else if (hasApiKey) {
      // Already has API key - go to chat
      navigate('/chat');
    } else {
      // New user - go to API key setup
      navigate('/api-key');
    }
  };

  const handleBack = () => {
    if (mode === 'update' || mode === 'restart') {
      navigate('/settings');
    } else {
      navigate('/permissions');
    }
  };

  const getTitleForMode = () => {
    switch (mode) {
      case 'update':
        return 'Update Your Memory';
      case 'restart':
        return 'Let\'s Start Fresh';
      default:
        return 'Let\'s Get to Know You';
    }
  };

  const getSubtitleForMode = () => {
    switch (mode) {
      case 'update':
        return 'Tell me more about yourself or update anything that\'s changed.';
      case 'restart':
        return 'I\'ve cleared your memory. Let\'s build a new profile together.';
      default:
        return 'A quick chat to help Trace personalize your experience.';
    }
  };

  const phaseIndex = getPhaseIndex(phase);
  const showContinueButton = isComplete || isReadyToContinue || phase === 'complete';

  return (
    <OnboardingLayout
      currentStep={mode === 'initial' ? 3 : undefined}
      totalSteps={mode === 'initial' ? 5 : undefined}
      showBack
      onBack={handleBack}
    >
      <style>{typingAnimationStyle}</style>

      <div style={styles.container}>
        <h1 style={styles.title}>{getTitleForMode()}</h1>
        <p style={styles.subtitle}>{getSubtitleForMode()}</p>

        {/* Phase progress indicator */}
        {mode === 'initial' && (
          <div style={styles.phaseIndicator}>
            {PHASES.slice(0, -1).map((p, idx) => (
              <div
                key={p}
                style={{
                  ...styles.phaseDot,
                  ...(idx === phaseIndex ? styles.phaseDotActive : {}),
                  ...(idx < phaseIndex ? styles.phaseDotCompleted : {}),
                }}
              />
            ))}
          </div>
        )}

        {/* Memory summary for update mode */}
        {mode === 'update' && memorySummary && (
          <div style={styles.memorySummary}>
            <div style={styles.memorySummaryTitle}>What I know about you:</div>
            {memorySummary}
          </div>
        )}

        {/* Chat container */}
        <div style={styles.chatContainer}>
          <div style={styles.messagesContainer}>
            {messages.map((msg, idx) => (
              <div
                key={idx}
                style={{
                  ...styles.messageRow,
                  ...(msg.role === 'user' ? styles.messageRowUser : {}),
                }}
              >
                <div
                  style={{
                    ...styles.avatar,
                    ...(msg.role === 'assistant' ? styles.avatarAssistant : styles.avatarUser),
                  }}
                >
                  {msg.role === 'assistant' ? 'T' : 'U'}
                </div>
                <div
                  style={{
                    ...styles.messageBubble,
                    ...(msg.role === 'assistant' ? styles.messageBubbleAssistant : styles.messageBubbleUser),
                  }}
                >
                  {msg.content}
                </div>
              </div>
            ))}
            {isLoading && (
              <div style={styles.messageRow}>
                <div style={{ ...styles.avatar, ...styles.avatarAssistant }}>T</div>
                <div style={styles.typingIndicator}>
                  <div style={{ ...styles.typingDot, animationDelay: '0s' }} />
                  <div style={{ ...styles.typingDot, animationDelay: '0.2s' }} />
                  <div style={{ ...styles.typingDot, animationDelay: '0.4s' }} />
                </div>
              </div>
            )}
            <div ref={messagesEndRef} />
          </div>

          {/* Input area */}
          {!showContinueButton && (
            <div style={styles.inputContainer}>
              <textarea
                ref={inputRef}
                value={inputValue}
                onChange={(e) => setInputValue(e.target.value)}
                onKeyDown={handleKeyDown}
                placeholder="Type your message..."
                style={styles.input}
                rows={1}
                disabled={isLoading}
              />
              <button
                onClick={handleSend}
                disabled={!inputValue.trim() || isLoading}
                style={{
                  ...styles.sendButton,
                  ...(!inputValue.trim() || isLoading ? styles.sendButtonDisabled : {}),
                }}
              >
                <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <path d="M22 2L11 13M22 2L15 22L11 13L2 9L22 2Z" />
                </svg>
              </button>
            </div>
          )}
        </div>

        {/* Action buttons */}
        <div style={styles.buttonContainer}>
          {!showContinueButton ? (
            <button style={styles.skipButton} onClick={handleSkip}>
              Skip for now
            </button>
          ) : (
            <button
              style={{
                ...styles.continueButton,
                ...(isFinalizing ? styles.continueButtonDisabled : {}),
              }}
              onClick={handleContinue}
              disabled={isFinalizing}
            >
              {isFinalizing ? 'Saving...' : 'Continue'}
            </button>
          )}
        </div>
      </div>
    </OnboardingLayout>
  );
};

export default UserProfile;
