import React from 'react';
import { useNavigate } from 'react-router-dom';
import { OnboardingLayout } from './OnboardingLayout';

const styles: Record<string, React.CSSProperties> = {
  logo: {
    fontSize: 56,
    fontWeight: 700,
    letterSpacing: 8,
    background: 'linear-gradient(135deg, #00d4ff 0%, #7c3aed 50%, #f472b6 100%)',
    WebkitBackgroundClip: 'text',
    WebkitTextFillColor: 'transparent',
    marginBottom: 12,
  },
  tagline: {
    fontSize: 18,
    color: 'var(--text-secondary)',
    marginBottom: 48,
    textAlign: 'center',
  },
  featuresContainer: {
    display: 'flex',
    flexDirection: 'column',
    gap: 20,
    marginBottom: 48,
    width: '100%',
  },
  featureCard: {
    display: 'flex',
    alignItems: 'flex-start',
    gap: 16,
    padding: '20px 24px',
    backgroundColor: 'var(--bg-secondary)',
    borderRadius: 12,
    border: '1px solid var(--border)',
    transition: 'all 0.2s ease',
  },
  featureIcon: {
    fontSize: 28,
    flexShrink: 0,
    width: 44,
    height: 44,
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: 'rgba(0, 122, 255, 0.1)',
    borderRadius: 10,
  },
  featureContent: {
    flex: 1,
  },
  featureTitle: {
    fontSize: 16,
    fontWeight: 600,
    color: 'var(--text-primary)',
    marginBottom: 4,
  },
  featureDescription: {
    fontSize: 14,
    color: 'var(--text-secondary)',
    lineHeight: 1.5,
  },
  permissionNote: {
    fontSize: 14,
    color: 'var(--text-secondary)',
    textAlign: 'center',
    marginBottom: 32,
    lineHeight: 1.6,
  },
  button: {
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
};

const features = [
  {
    icon: (
      <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="#00d4ff" strokeWidth="2">
        <rect x="3" y="3" width="18" height="18" rx="2" ry="2" />
        <circle cx="8.5" cy="8.5" r="1.5" />
        <polyline points="21 15 16 10 5 21" />
      </svg>
    ),
    title: 'Automatic Screen Capture',
    description: 'Quietly captures your screen activity in the background, creating a visual record of your work.',
  },
  {
    icon: (
      <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="#7c3aed" strokeWidth="2">
        <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
        <polyline points="14 2 14 8 20 8" />
        <line x1="16" y1="13" x2="8" y2="13" />
        <line x1="16" y1="17" x2="8" y2="17" />
        <polyline points="10 9 9 9 8 9" />
      </svg>
    ),
    title: 'Intelligent Summaries',
    description: 'AI analyzes your activity and generates hourly and daily notes, highlighting what matters most.',
  },
  {
    icon: (
      <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="#f472b6" strokeWidth="2">
        <circle cx="11" cy="11" r="8" />
        <line x1="21" y1="21" x2="16.65" y2="16.65" />
      </svg>
    ),
    title: 'Searchable Memory',
    description: 'Ask questions about your past activity in natural language. Find anything you\'ve worked on.',
  },
];

export const Welcome: React.FC = () => {
  const navigate = useNavigate();

  return (
    <OnboardingLayout currentStep={1} totalSteps={5}>
      <h1 style={styles.logo}>TRACE</h1>
      <p style={styles.tagline}>Your digital activity, organized and searchable</p>

      <div style={styles.featuresContainer}>
        {features.map((feature, index) => (
          <div key={index} style={styles.featureCard}>
            <div style={styles.featureIcon}>{feature.icon}</div>
            <div style={styles.featureContent}>
              <div style={styles.featureTitle}>{feature.title}</div>
              <div style={styles.featureDescription}>{feature.description}</div>
            </div>
          </div>
        ))}
      </div>

      <p style={styles.permissionNote}>
        To make this work, Trace needs a few permissions.<br />
        We&apos;ll guide you through each one.
      </p>

      <button
        style={styles.button}
        onClick={() => navigate('/permissions')}
        onMouseEnter={(e) => {
          e.currentTarget.style.transform = 'translateY(-2px)';
          e.currentTarget.style.boxShadow = '0 6px 16px rgba(0, 122, 255, 0.4)';
        }}
        onMouseLeave={(e) => {
          e.currentTarget.style.transform = 'translateY(0)';
          e.currentTarget.style.boxShadow = '0 4px 12px rgba(0, 122, 255, 0.3)';
        }}
      >
        Get Started
      </button>
    </OnboardingLayout>
  );
};

export default Welcome;
