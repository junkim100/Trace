import React from 'react';
import { useNavigate } from 'react-router-dom';

interface OnboardingLayoutProps {
  currentStep: number;
  totalSteps: number;
  children: React.ReactNode;
  showBack?: boolean;
  onBack?: () => void;
}

const styles: Record<string, React.CSSProperties> = {
  container: {
    display: 'flex',
    flexDirection: 'column',
    minHeight: '100vh',
    backgroundColor: 'var(--bg-primary)',
    color: 'var(--text-primary)',
  },
  titlebar: {
    height: 38,
    backgroundColor: 'transparent',
    flexShrink: 0,
  },
  content: {
    flex: 1,
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'center',
    justifyContent: 'center',
    padding: '0 40px 40px 40px',
    animation: 'fadeIn 0.4s ease-out',
  },
  stepIndicator: {
    display: 'flex',
    gap: 12,
    marginBottom: 40,
  },
  stepDot: {
    width: 10,
    height: 10,
    borderRadius: '50%',
    backgroundColor: 'var(--border)',
    transition: 'all 0.3s ease',
  },
  stepDotActive: {
    width: 10,
    height: 10,
    borderRadius: '50%',
    backgroundColor: 'var(--accent)',
    boxShadow: '0 0 10px rgba(0, 122, 255, 0.5)',
    transition: 'all 0.3s ease',
  },
  stepDotCompleted: {
    width: 10,
    height: 10,
    borderRadius: '50%',
    backgroundColor: '#34c759',
    transition: 'all 0.3s ease',
  },
  backButton: {
    position: 'absolute',
    top: 50,
    left: 20,
    display: 'flex',
    alignItems: 'center',
    gap: 6,
    padding: '8px 16px',
    backgroundColor: 'transparent',
    border: '1px solid var(--border)',
    borderRadius: 8,
    color: 'var(--text-secondary)',
    fontSize: 14,
    cursor: 'pointer',
    transition: 'all 0.2s ease',
  },
  childrenWrapper: {
    width: '100%',
    maxWidth: 500,
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'center',
  },
};

export const OnboardingLayout: React.FC<OnboardingLayoutProps> = ({
  currentStep,
  totalSteps,
  children,
  showBack = false,
  onBack,
}) => {
  const navigate = useNavigate();

  const handleBack = () => {
    if (onBack) {
      onBack();
    } else {
      navigate(-1);
    }
  };

  return (
    <div style={styles.container}>
      <div style={styles.titlebar} className="titlebar" />

      {showBack && (
        <button
          style={styles.backButton}
          className="no-drag"
          onClick={handleBack}
          onMouseEnter={(e) => {
            e.currentTarget.style.backgroundColor = 'var(--bg-secondary)';
            e.currentTarget.style.borderColor = 'var(--text-secondary)';
          }}
          onMouseLeave={(e) => {
            e.currentTarget.style.backgroundColor = 'transparent';
            e.currentTarget.style.borderColor = 'var(--border)';
          }}
        >
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M19 12H5M12 19l-7-7 7-7" />
          </svg>
          Back
        </button>
      )}

      <div style={styles.content} className="onboarding-fade-in">
        <div style={styles.stepIndicator}>
          {Array.from({ length: totalSteps }, (_, i) => {
            const stepNum = i + 1;
            let dotStyle = styles.stepDot;
            if (stepNum < currentStep) {
              dotStyle = styles.stepDotCompleted;
            } else if (stepNum === currentStep) {
              dotStyle = styles.stepDotActive;
            }
            return <div key={i} style={dotStyle} />;
          })}
        </div>

        <div style={styles.childrenWrapper}>
          {children}
        </div>
      </div>
    </div>
  );
};

export default OnboardingLayout;
