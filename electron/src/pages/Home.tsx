import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';

function Home() {
  const navigate = useNavigate();
  const [pythonReady, setPythonReady] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);
  const [statusText, setStatusText] = useState<string>('Starting backend...');

  useEffect(() => {
    if (!window.traceAPI) {
      setError('Not running in Electron');
      return;
    }

    // Poll for Python backend readiness
    const checkSetup = async () => {
      try {
        const ready = await window.traceAPI.python.isReady();
        setPythonReady(ready);

        if (ready) {
          setStatusText('Checking setup...');

          // Check if API key is set
          const settings = await window.traceAPI.settings.get();

          if (!settings.has_api_key) {
            // First launch - go to onboarding
            navigate('/onboarding/welcome');
            return;
          }

          // API key exists, check permissions
          const permissions = await window.traceAPI.permissions.checkAll();

          // Check if required permissions are granted
          const requiredGranted =
            permissions.screen_recording.status === 'granted' &&
            permissions.accessibility.status === 'granted';

          if (!requiredGranted) {
            // Permissions not granted - go to permissions page
            // Pass flag indicating this is an upgrade (API key already exists)
            navigate('/permissions', { state: { isUpgrade: true } });
          } else {
            // Check if user profile exists
            const profile = await window.traceAPI.settings.get('user_profile') as {
              name?: string;
              interests?: string;
            } | null;

            const hasProfile = profile && (profile.name || profile.interests);

            if (!hasProfile) {
              // No profile yet - show profile setup
              navigate('/onboarding/profile');
            } else {
              // All good - go to chat
              navigate('/chat');
            }
          }
        }
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Unknown error');
      }
    };

    // Check immediately and then poll every 2 seconds until ready
    checkSetup();
    const interval = setInterval(() => {
      if (!pythonReady) {
        checkSetup();
      }
    }, 2000);

    return () => clearInterval(interval);
  }, [pythonReady, navigate]);

  return (
    <div style={styles.container}>
      <div className="titlebar" style={styles.titlebar} />
      <main style={styles.main}>
        <h1 style={styles.logoText}>TRACE</h1>
        <p style={styles.subtitle}>
          Your digital activity, organized and searchable.
        </p>
        <div style={styles.loadingContainer}>
          <div style={styles.spinner} />
          <p style={styles.loadingText}>{statusText}</p>
        </div>
        {error && (
          <div style={styles.errorCard}>
            <p style={styles.errorText}>{error}</p>
          </div>
        )}
      </main>
    </div>
  );
}

const styles: Record<string, React.CSSProperties> = {
  container: {
    flex: 1,
    display: 'flex',
    flexDirection: 'column',
    minHeight: '100vh',
    backgroundColor: 'var(--bg-primary)',
  },
  titlebar: {
    minHeight: '52px',
  },
  main: {
    flex: 1,
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'center',
    justifyContent: 'center',
    padding: '2rem',
  },
  logoText: {
    fontSize: '3rem',
    fontWeight: 700,
    letterSpacing: '0.15em',
    marginBottom: '0.5rem',
    background: 'linear-gradient(135deg, #00d4ff 0%, #7b68ee 50%, #ff6b9d 100%)',
    WebkitBackgroundClip: 'text',
    WebkitTextFillColor: 'transparent',
    backgroundClip: 'text',
  },
  subtitle: {
    fontSize: '1.25rem',
    color: 'var(--text-secondary)',
    marginBottom: '2rem',
  },
  loadingContainer: {
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'center',
    gap: '1rem',
  },
  spinner: {
    width: '32px',
    height: '32px',
    border: '3px solid var(--border)',
    borderTopColor: 'var(--accent)',
    borderRadius: '50%',
    animation: 'spin 1s linear infinite',
  },
  loadingText: {
    color: 'var(--text-secondary)',
    fontSize: '0.9rem',
  },
  errorCard: {
    background: 'rgba(255, 59, 48, 0.1)',
    borderRadius: '12px',
    padding: '1rem',
    border: '1px solid rgba(255, 59, 48, 0.3)',
    marginTop: '1rem',
  },
  errorText: {
    color: '#ff6b6b',
    fontSize: '0.875rem',
    margin: 0,
  },
};

export default Home;
