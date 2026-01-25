import React, { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { OnboardingLayout } from './OnboardingLayout';

const styles: Record<string, React.CSSProperties> = {
  successIcon: {
    width: 100,
    height: 100,
    borderRadius: '50%',
    backgroundColor: 'rgba(52, 199, 89, 0.1)',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    marginBottom: 32,
    animation: 'fadeIn 0.5s ease-out',
  },
  title: {
    fontSize: 32,
    fontWeight: 700,
    marginBottom: 12,
    background: 'linear-gradient(135deg, #34c759, #00d4ff)',
    WebkitBackgroundClip: 'text',
    WebkitTextFillColor: 'transparent',
    textAlign: 'center',
  },
  subtitle: {
    fontSize: 18,
    color: 'var(--text-secondary)',
    marginBottom: 40,
    textAlign: 'center',
    lineHeight: 1.6,
  },
  tipsContainer: {
    width: '100%',
    marginBottom: 40,
  },
  tipCard: {
    display: 'flex',
    alignItems: 'flex-start',
    gap: 16,
    padding: 20,
    backgroundColor: 'var(--bg-secondary)',
    borderRadius: 12,
    marginBottom: 12,
    border: '1px solid var(--border)',
  },
  tipIcon: {
    width: 40,
    height: 40,
    borderRadius: 10,
    backgroundColor: 'rgba(0, 122, 255, 0.1)',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    flexShrink: 0,
  },
  tipContent: {
    flex: 1,
  },
  tipTitle: {
    fontSize: 15,
    fontWeight: 600,
    color: 'var(--text-primary)',
    marginBottom: 4,
  },
  tipDescription: {
    fontSize: 14,
    color: 'var(--text-secondary)',
    lineHeight: 1.5,
  },
  button: {
    padding: '16px 56px',
    fontSize: 17,
    fontWeight: 600,
    backgroundColor: 'var(--accent)',
    color: 'white',
    border: 'none',
    borderRadius: 12,
    cursor: 'pointer',
    transition: 'all 0.2s ease',
    boxShadow: '0 4px 16px rgba(0, 122, 255, 0.4)',
  },
  confetti: {
    position: 'fixed',
    top: 0,
    left: 0,
    width: '100%',
    height: '100%',
    pointerEvents: 'none',
    zIndex: 100,
  },
};

const tips = [
  {
    icon: (
      <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#00d4ff" strokeWidth="2">
        <rect x="3" y="3" width="7" height="7" />
        <rect x="14" y="3" width="7" height="7" />
        <rect x="14" y="14" width="7" height="7" />
        <rect x="3" y="14" width="7" height="7" />
      </svg>
    ),
    title: 'Menu Bar Access',
    description: 'Click the Trace icon in your menu bar anytime to access settings or check status.',
  },
  {
    icon: (
      <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#7c3aed" strokeWidth="2">
        <circle cx="12" cy="12" r="10" />
        <polyline points="12 6 12 12 16 14" />
      </svg>
    ),
    title: 'Hourly Summaries',
    description: 'Your first summary will be ready after an hour of activity. Check back soon!',
  },
  {
    icon: (
      <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#f472b6" strokeWidth="2">
        <circle cx="11" cy="11" r="8" />
        <line x1="21" y1="21" x2="16.65" y2="16.65" />
      </svg>
    ),
    title: 'Ask Anything',
    description: 'Use the chat to search your activity history using natural language.',
  },
];

export const SetupComplete: React.FC = () => {
  const navigate = useNavigate();
  const [showConfetti, setShowConfetti] = useState(true);

  useEffect(() => {
    // Hide confetti after animation
    const timer = setTimeout(() => setShowConfetti(false), 3000);
    return () => clearTimeout(timer);
  }, []);

  const handleOpenTrace = () => {
    navigate('/chat');
  };

  return (
    <OnboardingLayout currentStep={5} totalSteps={5}>
      {showConfetti && (
        <div style={styles.confetti}>
          {/* Simple confetti effect using CSS */}
          <style>
            {`
              @keyframes confetti-fall {
                0% { transform: translateY(-100vh) rotate(0deg); opacity: 1; }
                100% { transform: translateY(100vh) rotate(720deg); opacity: 0; }
              }
              .confetti-piece {
                position: absolute;
                width: 10px;
                height: 10px;
                animation: confetti-fall 3s ease-out forwards;
              }
            `}
          </style>
          {Array.from({ length: 50 }).map((_, i) => (
            <div
              key={i}
              className="confetti-piece"
              style={{
                left: `${Math.random() * 100}%`,
                backgroundColor: ['#00d4ff', '#7c3aed', '#f472b6', '#34c759', '#ff9500'][i % 5],
                borderRadius: Math.random() > 0.5 ? '50%' : '0',
                animationDelay: `${Math.random() * 0.5}s`,
              }}
            />
          ))}
        </div>
      )}

      <div style={styles.successIcon}>
        <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="#34c759" strokeWidth="2.5">
          <polyline points="20 6 9 17 4 12" />
        </svg>
      </div>

      <h1 style={styles.title}>You&apos;re All Set!</h1>
      <p style={styles.subtitle}>
        Trace is now running in the background,<br />
        capturing and organizing your digital activity.
      </p>

      <div style={styles.tipsContainer}>
        {tips.map((tip, index) => (
          <div key={index} style={styles.tipCard}>
            <div style={styles.tipIcon}>{tip.icon}</div>
            <div style={styles.tipContent}>
              <div style={styles.tipTitle}>{tip.title}</div>
              <div style={styles.tipDescription}>{tip.description}</div>
            </div>
          </div>
        ))}
      </div>

      <button
        style={styles.button}
        onClick={handleOpenTrace}
        onMouseEnter={(e) => {
          e.currentTarget.style.transform = 'translateY(-2px)';
          e.currentTarget.style.boxShadow = '0 6px 20px rgba(0, 122, 255, 0.5)';
        }}
        onMouseLeave={(e) => {
          e.currentTarget.style.transform = 'translateY(0)';
          e.currentTarget.style.boxShadow = '0 4px 16px rgba(0, 122, 255, 0.4)';
        }}
      >
        Open Trace
      </button>
    </OnboardingLayout>
  );
};

export default SetupComplete;
