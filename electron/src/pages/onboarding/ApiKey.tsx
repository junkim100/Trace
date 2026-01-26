import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { OnboardingLayout } from './OnboardingLayout';

const styles: Record<string, React.CSSProperties> = {
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
    marginBottom: 40,
    textAlign: 'center',
    lineHeight: 1.6,
  },
  card: {
    backgroundColor: 'var(--bg-secondary)',
    borderRadius: 16,
    padding: 32,
    width: '100%',
    border: '1px solid var(--border)',
    marginBottom: 32,
  },
  iconContainer: {
    width: 64,
    height: 64,
    backgroundColor: 'rgba(0, 122, 255, 0.1)',
    borderRadius: 16,
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    margin: '0 auto 24px auto',
  },
  inputGroup: {
    marginBottom: 20,
  },
  label: {
    display: 'block',
    fontSize: 14,
    fontWeight: 500,
    color: 'var(--text-primary)',
    marginBottom: 8,
  },
  inputWrapper: {
    position: 'relative',
    display: 'flex',
    alignItems: 'center',
  },
  input: {
    width: '100%',
    padding: '14px 48px 14px 16px',
    fontSize: 15,
    backgroundColor: 'rgba(0, 0, 0, 0.2)',
    border: '1px solid var(--border)',
    borderRadius: 10,
    color: 'var(--text-primary)',
    outline: 'none',
    transition: 'all 0.2s ease',
  },
  inputFocused: {
    borderColor: 'var(--accent)',
    boxShadow: '0 0 0 3px rgba(0, 122, 255, 0.1)',
  },
  inputError: {
    borderColor: '#ff3b30',
  },
  inputValid: {
    borderColor: '#34c759',
  },
  toggleButton: {
    position: 'absolute',
    right: 12,
    background: 'none',
    border: 'none',
    color: 'var(--text-secondary)',
    cursor: 'pointer',
    padding: 4,
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
  },
  validationIcon: {
    position: 'absolute',
    right: 44,
    display: 'flex',
    alignItems: 'center',
  },
  helpText: {
    fontSize: 13,
    color: 'var(--text-secondary)',
    marginTop: 12,
    lineHeight: 1.5,
  },
  link: {
    color: 'var(--accent)',
    textDecoration: 'none',
  },
  errorText: {
    fontSize: 13,
    color: '#ff3b30',
    marginTop: 8,
  },
  buttonContainer: {
    display: 'flex',
    gap: 12,
    justifyContent: 'center',
  },
  primaryButton: {
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
  primaryButtonDisabled: {
    opacity: 0.5,
    cursor: 'not-allowed',
  },
  validatingText: {
    fontSize: 13,
    color: 'var(--text-secondary)',
    marginTop: 16,
    textAlign: 'center',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 8,
  },
  spinner: {
    width: 16,
    height: 16,
    border: '2px solid var(--border)',
    borderTopColor: 'var(--accent)',
    borderRadius: '50%',
    animation: 'spin 1s linear infinite',
  },
};

export const ApiKey: React.FC = () => {
  const navigate = useNavigate();
  const [apiKey, setApiKey] = useState('');
  const [showKey, setShowKey] = useState(false);
  const [isValidating, setIsValidating] = useState(false);
  const [isValid, setIsValid] = useState<boolean | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isFocused, setIsFocused] = useState(false);

  const handleValidateAndContinue = async () => {
    if (!apiKey.trim()) {
      setError('Please enter your API key');
      return;
    }

    setIsValidating(true);
    setError(null);

    try {
      // Validate the API key
      const result = await window.traceAPI.settings.validateApiKey(apiKey);

      if (result.valid) {
        // Save the API key
        await window.traceAPI.settings.setApiKey(apiKey);
        setIsValid(true);

        // Navigate to profile page after a brief delay to show success
        setTimeout(() => {
          navigate('/onboarding/profile');
        }, 500);
      } else {
        setIsValid(false);
        setError(result.error || 'Invalid API key. Please check and try again.');
      }
    } catch (err) {
      setIsValid(false);
      setError(err instanceof Error ? err.message : 'Failed to validate API key');
    } finally {
      setIsValidating(false);
    }
  };

  const handleBack = () => {
    navigate('/permissions');
  };

  const handleKeyPress = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && apiKey.trim() && !isValidating) {
      handleValidateAndContinue();
    }
  };

  const getInputStyle = (): React.CSSProperties => {
    let style = { ...styles.input };
    if (isFocused) {
      style = { ...style, ...styles.inputFocused };
    }
    if (isValid === true) {
      style = { ...style, ...styles.inputValid };
    }
    if (isValid === false || error) {
      style = { ...style, ...styles.inputError };
    }
    return style;
  };

  return (
    <OnboardingLayout currentStep={3} totalSteps={5} showBack onBack={handleBack}>
      <h1 style={styles.title}>Connect to OpenAI</h1>
      <p style={styles.subtitle}>
        Trace uses OpenAI&apos;s API to analyze your activity<br />
        and generate intelligent summaries.
      </p>

      <div style={styles.card}>
        <div style={styles.iconContainer}>
          <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="#00d4ff" strokeWidth="2">
            <rect x="3" y="11" width="18" height="11" rx="2" ry="2" />
            <path d="M7 11V7a5 5 0 0 1 10 0v4" />
          </svg>
        </div>

        <div style={styles.inputGroup}>
          <label style={styles.label}>OpenAI API Key</label>
          <div style={styles.inputWrapper as React.CSSProperties}>
            <input
              type={showKey ? 'text' : 'password'}
              value={apiKey}
              onChange={(e) => {
                setApiKey(e.target.value);
                setIsValid(null);
                setError(null);
              }}
              onFocus={() => setIsFocused(true)}
              onBlur={() => setIsFocused(false)}
              onKeyPress={handleKeyPress}
              placeholder="sk-..."
              style={getInputStyle()}
              disabled={isValidating}
            />
            {isValid !== null && (
              <div style={styles.validationIcon as React.CSSProperties}>
                {isValid ? (
                  <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#34c759" strokeWidth="3">
                    <polyline points="20 6 9 17 4 12" />
                  </svg>
                ) : (
                  <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#ff3b30" strokeWidth="3">
                    <line x1="18" y1="6" x2="6" y2="18" />
                    <line x1="6" y1="6" x2="18" y2="18" />
                  </svg>
                )}
              </div>
            )}
            <button
              style={styles.toggleButton as React.CSSProperties}
              onClick={() => setShowKey(!showKey)}
              type="button"
            >
              {showKey ? (
                <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19m-6.72-1.07a3 3 0 1 1-4.24-4.24" />
                  <line x1="1" y1="1" x2="23" y2="23" />
                </svg>
              ) : (
                <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z" />
                  <circle cx="12" cy="12" r="3" />
                </svg>
              )}
            </button>
          </div>

          {error && <p style={styles.errorText}>{error}</p>}

          <p style={styles.helpText}>
            Don&apos;t have an API key?{' '}
            <a
              href="https://platform.openai.com/api-keys"
              target="_blank"
              rel="noopener noreferrer"
              style={styles.link}
              onClick={(e) => {
                e.preventDefault();
                window.traceAPI?.shell?.openExternal('https://platform.openai.com/api-keys');
              }}
            >
              Get one from OpenAI →
            </a>
          </p>
        </div>
      </div>

      <div style={styles.buttonContainer}>
        <button
          style={{
            ...styles.primaryButton,
            ...((!apiKey.trim() || isValidating) ? styles.primaryButtonDisabled : {}),
          }}
          onClick={handleValidateAndContinue}
          disabled={!apiKey.trim() || isValidating}
        >
          {isValidating ? 'Validating...' : 'Continue'}
        </button>
      </div>

      {isValidating && (
        <div style={styles.validatingText as React.CSSProperties}>
          <div style={styles.spinner} />
          Verifying your API key...
        </div>
      )}
    </OnboardingLayout>
  );
};

export default ApiKey;
