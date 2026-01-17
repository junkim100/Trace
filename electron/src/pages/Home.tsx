import { useState, useEffect } from 'react';
import type { BackendStatus } from '../types/trace-api';

function Home() {
  const [electronIpc, setElectronIpc] = useState<string>('Testing...');
  const [pythonReady, setPythonReady] = useState<boolean>(false);
  const [pythonPing, setPythonPing] = useState<string>('Waiting...');
  const [backendStatus, setBackendStatus] = useState<BackendStatus | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!window.traceAPI) {
      setElectronIpc('Not running in Electron');
      return;
    }

    // Test Electron IPC
    window.traceAPI
      .ping()
      .then((response) => {
        setElectronIpc(`OK: ${response}`);
      })
      .catch((err) => {
        setElectronIpc(`Error: ${err.message}`);
      });

    // Poll for Python backend readiness
    const checkPython = async () => {
      try {
        const ready = await window.traceAPI.python.isReady();
        setPythonReady(ready);

        if (ready) {
          // Test Python ping
          const pingResult = await window.traceAPI.python.ping();
          setPythonPing(`OK: ${pingResult}`);

          // Get backend status
          const status = await window.traceAPI.python.getStatus();
          setBackendStatus(status);
        }
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Unknown error');
      }
    };

    // Check immediately and then poll every 2 seconds until ready
    checkPython();
    const interval = setInterval(() => {
      if (!pythonReady) {
        checkPython();
      }
    }, 2000);

    return () => clearInterval(interval);
  }, [pythonReady]);

  return (
    <div style={styles.container}>
      <div className="titlebar" />
      <main style={styles.main}>
        <h1 style={styles.title}>Trace</h1>
        <p style={styles.subtitle}>
          Your digital activity, organized and searchable.
        </p>

        <div style={styles.statusGrid}>
          <div style={styles.statusCard}>
            <h3 style={styles.cardTitle}>Electron IPC</h3>
            <p style={styles.statusValue}>{electronIpc}</p>
            <p style={styles.statusLabel}>
              Platform: {window.traceAPI?.platform || 'Browser'}
            </p>
          </div>

          <div style={styles.statusCard}>
            <h3 style={styles.cardTitle}>Python Backend</h3>
            <p style={{ ...styles.statusValue, color: pythonReady ? '#00d4ff' : '#ff6b6b' }}>
              {pythonReady ? 'Connected' : 'Connecting...'}
            </p>
            <p style={styles.statusLabel}>Ping: {pythonPing}</p>
          </div>

          {backendStatus && (
            <div style={styles.statusCard}>
              <h3 style={styles.cardTitle}>Backend Info</h3>
              <p style={styles.statusValue}>v{backendStatus.version}</p>
              <p style={styles.statusLabel}>
                Python {backendStatus.python_version}
              </p>
              <p style={styles.statusLabel}>
                Uptime: {Math.floor(backendStatus.uptime_seconds)}s
              </p>
            </div>
          )}
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
  },
  main: {
    flex: 1,
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'center',
    justifyContent: 'center',
    padding: '2rem',
  },
  title: {
    fontSize: '3rem',
    fontWeight: 700,
    marginBottom: '0.5rem',
    background: 'linear-gradient(135deg, #007aff, #00d4ff)',
    WebkitBackgroundClip: 'text',
    WebkitTextFillColor: 'transparent',
  },
  subtitle: {
    fontSize: '1.25rem',
    color: '#a0a0a0',
    marginBottom: '2rem',
  },
  statusGrid: {
    display: 'flex',
    gap: '1rem',
    flexWrap: 'wrap',
    justifyContent: 'center',
  },
  statusCard: {
    background: '#2a2a2a',
    borderRadius: '12px',
    padding: '1.5rem',
    border: '1px solid #3a3a3a',
    minWidth: '200px',
  },
  cardTitle: {
    fontSize: '0.875rem',
    color: '#707070',
    marginBottom: '0.5rem',
    textTransform: 'uppercase',
    letterSpacing: '0.05em',
  },
  statusValue: {
    fontSize: '1.25rem',
    color: '#00d4ff',
    marginBottom: '0.5rem',
  },
  statusLabel: {
    fontSize: '0.875rem',
    color: '#707070',
  },
  errorCard: {
    background: '#3a2020',
    borderRadius: '12px',
    padding: '1rem',
    border: '1px solid #5a3030',
    marginTop: '1rem',
  },
  errorText: {
    color: '#ff6b6b',
    fontSize: '0.875rem',
  },
};

export default Home;
