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
    marginBottom: 32,
    textAlign: 'center',
    lineHeight: 1.6,
  },
  card: {
    backgroundColor: 'var(--bg-secondary)',
    borderRadius: 16,
    padding: 32,
    width: '100%',
    border: '1px solid var(--border)',
    marginBottom: 24,
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
  input: {
    width: '100%',
    padding: '12px 16px',
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
  textarea: {
    width: '100%',
    padding: '12px 16px',
    fontSize: 15,
    backgroundColor: 'rgba(0, 0, 0, 0.2)',
    border: '1px solid var(--border)',
    borderRadius: 10,
    color: 'var(--text-primary)',
    outline: 'none',
    transition: 'all 0.2s ease',
    resize: 'vertical' as const,
    minHeight: 80,
    fontFamily: 'inherit',
  },
  note: {
    fontSize: 13,
    color: 'var(--text-secondary)',
    marginTop: 24,
    textAlign: 'center',
    lineHeight: 1.5,
    fontStyle: 'italic',
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
};

interface ProfileField {
  key: string;
  label: string;
  placeholder: string;
  type: 'input' | 'textarea';
}

const profileFields: ProfileField[] = [
  {
    key: 'name',
    label: 'Your Name',
    placeholder: 'e.g., Alex Chen',
    type: 'input',
  },
  {
    key: 'age',
    label: 'Age',
    placeholder: 'e.g., 28',
    type: 'input',
  },
  {
    key: 'interests',
    label: 'Interests & Hobbies',
    placeholder: 'e.g., software development, photography, hiking, cooking',
    type: 'textarea',
  },
  {
    key: 'languages',
    label: 'Languages You Speak',
    placeholder: 'e.g., English, Spanish, Mandarin',
    type: 'input',
  },
  {
    key: 'additional_info',
    label: 'Anything else about you',
    placeholder: 'e.g., I work as a product manager at a tech startup, prefer working late at night',
    type: 'textarea',
  },
];

export const UserProfile: React.FC = () => {
  const navigate = useNavigate();
  const [profile, setProfile] = useState<Record<string, string>>({
    name: '',
    age: '',
    interests: '',
    languages: '',
    additional_info: '',
  });
  const [focusedField, setFocusedField] = useState<string | null>(null);
  const [isSaving, setIsSaving] = useState(false);

  const handleChange = (key: string, value: string) => {
    setProfile((prev) => ({ ...prev, [key]: value }));
  };

  const handleContinue = async () => {
    setIsSaving(true);
    try {
      // Save each profile field
      for (const [key, value] of Object.entries(profile)) {
        if (value.trim()) {
          await window.traceAPI.settings.set(`user_profile.${key}`, value.trim());
        }
      }
      navigate('/onboarding/api-key');
    } catch (err) {
      console.error('Failed to save profile:', err);
      // Still navigate even if save fails - it's optional
      navigate('/onboarding/api-key');
    } finally {
      setIsSaving(false);
    }
  };

  const handleSkip = () => {
    navigate('/onboarding/api-key');
  };

  const handleBack = () => {
    navigate('/permissions');
  };

  const getInputStyle = (key: string): React.CSSProperties => {
    const baseStyle = profileFields.find(f => f.key === key)?.type === 'textarea'
      ? styles.textarea
      : styles.input;
    if (focusedField === key) {
      return { ...baseStyle, ...styles.inputFocused };
    }
    return baseStyle;
  };

  return (
    <OnboardingLayout currentStep={3} totalSteps={5} showBack onBack={handleBack}>
      <h1 style={styles.title}>Tell Us About Yourself</h1>
      <p style={styles.subtitle}>
        Help Trace personalize your activity notes.<br />
        All fields are optional.
      </p>

      <div style={styles.card}>
        <div style={styles.iconContainer}>
          <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="#00d4ff" strokeWidth="2">
            <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2" />
            <circle cx="12" cy="7" r="4" />
          </svg>
        </div>

        {profileFields.map((field) => (
          <div key={field.key} style={styles.inputGroup}>
            <label style={styles.label}>{field.label}</label>
            {field.type === 'textarea' ? (
              <textarea
                value={profile[field.key]}
                onChange={(e) => handleChange(field.key, e.target.value)}
                onFocus={() => setFocusedField(field.key)}
                onBlur={() => setFocusedField(null)}
                placeholder={field.placeholder}
                style={getInputStyle(field.key)}
              />
            ) : (
              <input
                type="text"
                value={profile[field.key]}
                onChange={(e) => handleChange(field.key, e.target.value)}
                onFocus={() => setFocusedField(field.key)}
                onBlur={() => setFocusedField(null)}
                placeholder={field.placeholder}
                style={getInputStyle(field.key)}
              />
            )}
          </div>
        ))}

        <p style={styles.note}>
          You can update this information anytime in Settings.
        </p>
      </div>

      <div style={styles.buttonContainer}>
        <button
          style={styles.skipButton}
          onClick={handleSkip}
          disabled={isSaving}
        >
          Skip
        </button>
        <button
          style={styles.primaryButton}
          onClick={handleContinue}
          disabled={isSaving}
        >
          {isSaving ? 'Saving...' : 'Continue'}
        </button>
      </div>
    </OnboardingLayout>
  );
};

export default UserProfile;
