import { useState, useEffect, useCallback } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import type {
  AllPermissionsState,
  PermissionType,
  PermissionState,
  PermissionInstructions,
  PermissionStatusType,
} from '../../types/trace-api';

// Permission icons
const PermissionIcons: Record<PermissionType, JSX.Element> = {
  screen_recording: (
    <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="#00d4ff" strokeWidth="2">
      <rect x="2" y="3" width="20" height="14" rx="2" ry="2" />
      <line x1="8" y1="21" x2="16" y2="21" />
      <line x1="12" y1="17" x2="12" y2="21" />
    </svg>
  ),
  accessibility: (
    <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="#7c3aed" strokeWidth="2">
      <circle cx="12" cy="4" r="2" />
      <path d="M12 6v6" />
      <path d="M8 10l4 4 4-4" />
      <path d="M6 20l6-6 6 6" />
    </svg>
  ),
  location: (
    <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="#f472b6" strokeWidth="2">
      <path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0 1 18 0z" />
      <circle cx="12" cy="10" r="3" />
    </svg>
  ),
};

interface PermissionCardProps {
  permission: PermissionState;
  instructions: PermissionInstructions | null;
  onOpenSettings: () => void;
  onRequest?: () => void;
  isLoading: boolean;
  icon: JSX.Element;
}

function PermissionCard({
  permission,
  instructions,
  onOpenSettings,
  onRequest,
  isLoading,
  icon,
}: PermissionCardProps) {
  const statusColors: Record<PermissionStatusType, string> = {
    granted: '#34c759',
    denied: '#ff3b30',
    not_determined: '#ff9500',
    restricted: '#8e8e93',
  };

  const statusLabels: Record<PermissionStatusType, string> = {
    granted: 'Granted',
    denied: 'Denied',
    not_determined: 'Not Set',
    restricted: 'Restricted',
  };

  const statusColor = statusColors[permission.status] || '#8e8e93';
  const statusLabel = statusLabels[permission.status] || 'Unknown';

  return (
    <div style={styles.permissionCard}>
      <div style={styles.cardHeader}>
        <div style={styles.titleRow}>
          <div style={styles.iconContainer}>{icon}</div>
          <div>
            <h3 style={styles.permissionTitle}>{instructions?.title || permission.permission}</h3>
            {permission.required ? (
              <span style={styles.requiredBadge}>Required</span>
            ) : (
              <span style={styles.optionalBadge}>Optional</span>
            )}
          </div>
        </div>
        <div style={{ ...styles.statusBadge, backgroundColor: statusColor }}>
          {statusLabel}
        </div>
      </div>

      <p style={styles.description}>
        {instructions?.description || 'Loading...'}
      </p>

      {permission.status !== 'granted' && instructions && (
        <div style={styles.stepsContainer}>
          <h4 style={styles.stepsTitle}>How to enable:</h4>
          <ol style={styles.stepsList}>
            {instructions.steps.map((step, index) => (
              <li key={index} style={styles.step}>{step}</li>
            ))}
          </ol>
        </div>
      )}

      {permission.status !== 'granted' && (
        <div style={styles.buttonRow}>
          <button
            style={styles.primaryButton}
            onClick={onOpenSettings}
            disabled={isLoading}
          >
            Open System Settings
          </button>
          {onRequest && permission.can_request && (
            <button
              style={styles.secondaryButton}
              onClick={onRequest}
              disabled={isLoading}
            >
              Request Permission
            </button>
          )}
        </div>
      )}

      {permission.status === 'granted' && (
        <div style={styles.grantedMessage}>
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#34c759" strokeWidth="3">
            <polyline points="20 6 9 17 4 12" />
          </svg>
          Permission granted
        </div>
      )}

      {instructions?.requires_restart && permission.status === 'denied' && (
        <p style={styles.restartWarning}>
          Note: You may need to restart Trace after granting this permission.
        </p>
      )}
    </div>
  );
}

// Polling interval when actively waiting for permission changes
const ACTIVE_POLL_INTERVAL = 1000; // 1 second
// Polling interval when idle (just checking periodically)
const IDLE_POLL_INTERVAL = 5000; // 5 seconds

function Permissions() {
  const navigate = useNavigate();
  const location = useLocation();
  // Check if this is an upgrade flow (user already has API key set)
  const isUpgrade = (location.state as { isUpgrade?: boolean })?.isUpgrade ?? false;

  const [permissionsState, setPermissionsState] = useState<AllPermissionsState | null>(null);
  const [instructions, setInstructions] = useState<Record<PermissionType, PermissionInstructions | null>>({
    screen_recording: null,
    accessibility: null,
    location: null,
  });
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [pythonReady, setPythonReady] = useState(false);
  const [isActivelyWaiting, setIsActivelyWaiting] = useState(false);

  const checkPermissions = useCallback(async (silent = false) => {
    if (!window.traceAPI?.permissions) return;

    try {
      if (!silent) setIsLoading(true);
      const state = await window.traceAPI.permissions.checkAll();

      setPermissionsState(state);
      setError(null);

      // If all permissions are now granted, stop active polling
      if (state.all_granted) {
        setIsActivelyWaiting(false);
      }
    } catch (err) {
      if (!silent) {
        setError(err instanceof Error ? err.message : 'Failed to check permissions');
      }
    } finally {
      if (!silent) setIsLoading(false);
    }
  }, []);

  const loadInstructions = useCallback(async () => {
    if (!window.traceAPI?.permissions) return;

    const permissions: PermissionType[] = ['screen_recording', 'accessibility', 'location'];

    for (const perm of permissions) {
      try {
        const instr = await window.traceAPI.permissions.getInstructions(perm);
        setInstructions(prev => ({ ...prev, [perm]: instr }));
      } catch (err) {
        console.error(`Failed to load instructions for ${perm}:`, err);
      }
    }
  }, []);

  // Check permissions and load instructions on mount
  useEffect(() => {
    if (!window.traceAPI) return;

    checkPermissions();
    loadInstructions();
  }, [checkPermissions, loadInstructions]);

  // Poll for Python backend readiness
  useEffect(() => {
    if (!window.traceAPI || pythonReady) return;

    const checkPython = async () => {
      try {
        const ready = await window.traceAPI.python.isReady();
        if (ready) setPythonReady(true);
      } catch {
        // Ignore errors during polling
      }
    };

    checkPython();
    const interval = setInterval(checkPython, 2000);

    return () => clearInterval(interval);
  }, [pythonReady]);

  // Active polling when waiting for permission changes
  useEffect(() => {
    if (permissionsState?.all_granted) return;

    const pollInterval = isActivelyWaiting ? ACTIVE_POLL_INTERVAL : IDLE_POLL_INTERVAL;

    const interval = setInterval(() => {
      checkPermissions(true);
    }, pollInterval);

    return () => clearInterval(interval);
  }, [isActivelyWaiting, permissionsState?.all_granted, checkPermissions]);

  const handleOpenSettings = async (permission: PermissionType) => {
    if (!window.traceAPI?.permissions) return;

    try {
      await window.traceAPI.permissions.openSettings(permission);
      // Start active polling - user is interacting with settings
      setIsActivelyWaiting(true);
      // Also do an immediate check after a short delay
      setTimeout(() => checkPermissions(true), 500);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to open settings');
    }
  };

  const handleRequestAccessibility = async () => {
    if (!window.traceAPI?.permissions) return;

    try {
      await window.traceAPI.permissions.requestAccessibility();
      setIsActivelyWaiting(true);
      setTimeout(() => checkPermissions(true), 500);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to request permission');
    }
  };

  const handleRequestLocation = async () => {
    if (!window.traceAPI?.permissions) return;

    try {
      await window.traceAPI.permissions.requestLocation();
      setIsActivelyWaiting(true);
      setTimeout(() => checkPermissions(true), 500);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to request permission');
    }
  };

  const handleContinue = () => {
    if (isUpgrade) {
      // Upgrade flow: API key already exists, go directly to chat
      navigate('/chat');
    } else {
      // Fresh install: Navigate to API key setup first (required for profile chat)
      navigate('/onboarding/api-key');
    }
  };

  const handleBack = () => {
    navigate('/onboarding/welcome');
  };

  // Check if required permissions are granted (screen_recording and accessibility)
  const requiredGranted = permissionsState?.screen_recording.status === 'granted' &&
                          permissionsState?.accessibility.status === 'granted';

  if (!window.traceAPI) {
    return (
      <div style={styles.pageContainer}>
        <div style={styles.titlebar} className="titlebar" />
        <div style={styles.scrollContainer}>
          <div style={styles.contentWrapper}>
            <h1 style={styles.title}>Permissions</h1>
            <p style={styles.subtitle}>Not running in Electron</p>
          </div>
        </div>
      </div>
    );
  }

  if (!pythonReady) {
    return (
      <div style={styles.pageContainer}>
        <div style={styles.titlebar} className="titlebar" />
        <div style={styles.scrollContainer}>
          <div style={styles.contentWrapper}>
            <div style={styles.loadingContainer}>
              <div style={styles.spinner} />
              <p style={styles.loadingText}>Connecting to backend...</p>
            </div>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div style={styles.pageContainer}>
      <div style={styles.titlebar} className="titlebar" />

      {!isUpgrade && (
        <button
          style={styles.backButton}
          className="no-drag"
          onClick={handleBack}
        >
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M19 12H5M12 19l-7-7 7-7" />
          </svg>
          Back
        </button>
      )}

      <div style={styles.scrollContainer}>
        <div style={styles.contentWrapper}>
          <h1 style={styles.title}>
            {isUpgrade ? 'Re-grant Permissions' : 'Grant Permissions'}
          </h1>
          <p style={styles.subtitle}>
            {isUpgrade
              ? 'After updating Trace, macOS requires you to re-grant permissions.'
              : 'Trace needs these permissions to capture your digital activity.'}
          </p>

          {error && (
            <div style={styles.errorCard}>
              <p style={styles.errorText}>{error}</p>
            </div>
          )}

          <div style={styles.permissionsList}>
            {permissionsState && (
              <>
                <PermissionCard
                  permission={permissionsState.screen_recording}
                  instructions={instructions.screen_recording}
                  onOpenSettings={() => handleOpenSettings('screen_recording')}
                  isLoading={isLoading}
                  icon={PermissionIcons.screen_recording}
                />

                <PermissionCard
                  permission={permissionsState.accessibility}
                  instructions={instructions.accessibility}
                  onOpenSettings={() => handleOpenSettings('accessibility')}
                  onRequest={handleRequestAccessibility}
                  isLoading={isLoading}
                  icon={PermissionIcons.accessibility}
                />

                <PermissionCard
                  permission={permissionsState.location}
                  instructions={instructions.location}
                  onOpenSettings={() => handleOpenSettings('location')}
                  onRequest={handleRequestLocation}
                  isLoading={isLoading}
                  icon={PermissionIcons.location}
                />
              </>
            )}
          </div>

          <div style={styles.footer}>
            <button
              style={{
                ...styles.continueButton,
                opacity: requiredGranted ? 1 : 0.5,
                cursor: requiredGranted ? 'pointer' : 'not-allowed',
              }}
              onClick={handleContinue}
              disabled={!requiredGranted}
            >
              {requiredGranted
                ? (isUpgrade ? 'Continue to Trace' : 'Next')
                : 'Grant Required Permissions'}
            </button>

            {isActivelyWaiting && !requiredGranted && (
              <div style={styles.pollingIndicator}>
                <span style={styles.pollingDot} />
                Checking for permission changes...
              </div>
            )}
          </div>

          {permissionsState?.requires_restart && (
            <p style={styles.restartNote}>
              Some permissions may require restarting Trace to take effect.
            </p>
          )}
        </div>
      </div>
    </div>
  );
}

const styles: Record<string, React.CSSProperties> = {
  pageContainer: {
    display: 'flex',
    flexDirection: 'column',
    height: '100%',
    backgroundColor: 'var(--bg-primary)',
    color: 'var(--text-primary)',
  },
  titlebar: {
    minHeight: 36,
    backgroundColor: 'transparent',
    flexShrink: 0,
  },
  backButton: {
    position: 'absolute',
    top: 44,
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
    zIndex: 10,
  },
  scrollContainer: {
    flex: 1,
    overflowY: 'auto',
    minHeight: 0,
    padding: '20px 40px 40px 40px',
  },
  contentWrapper: {
    maxWidth: 500,
    margin: '0 auto',
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'center',
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
    marginBottom: 32,
    textAlign: 'center',
  },
  loadingContainer: {
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'center',
    gap: 16,
  },
  spinner: {
    width: 32,
    height: 32,
    border: '3px solid var(--border)',
    borderTopColor: 'var(--accent)',
    borderRadius: '50%',
    animation: 'spin 1s linear infinite',
  },
  loadingText: {
    color: 'var(--text-secondary)',
    fontSize: 14,
  },
  permissionsList: {
    display: 'flex',
    flexDirection: 'column',
    gap: 16,
    width: '100%',
    marginBottom: 24,
  },
  permissionCard: {
    background: 'var(--bg-secondary)',
    borderRadius: 12,
    padding: 20,
    border: '1px solid var(--border)',
    transition: 'all 0.2s ease',
  },
  cardHeader: {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'flex-start',
    marginBottom: 12,
  },
  titleRow: {
    display: 'flex',
    alignItems: 'center',
    gap: 12,
  },
  iconContainer: {
    width: 48,
    height: 48,
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: 'rgba(0, 122, 255, 0.1)',
    borderRadius: 10,
    flexShrink: 0,
  },
  permissionTitle: {
    fontSize: 16,
    fontWeight: 600,
    color: 'var(--text-primary)',
    margin: 0,
    marginBottom: 4,
  },
  requiredBadge: {
    fontSize: 11,
    color: '#ff9500',
    padding: '2px 8px',
    borderRadius: 4,
    border: '1px solid #ff9500',
    fontWeight: 500,
  },
  optionalBadge: {
    fontSize: 11,
    color: 'var(--text-secondary)',
    padding: '2px 8px',
    borderRadius: 4,
    border: '1px solid var(--border)',
    fontWeight: 500,
  },
  statusBadge: {
    fontSize: 12,
    color: '#fff',
    padding: '4px 12px',
    borderRadius: 12,
    fontWeight: 500,
  },
  description: {
    fontSize: 14,
    color: 'var(--text-secondary)',
    marginBottom: 16,
    lineHeight: 1.5,
  },
  stepsContainer: {
    backgroundColor: 'rgba(0, 0, 0, 0.2)',
    borderRadius: 8,
    padding: 16,
    marginBottom: 16,
  },
  stepsTitle: {
    fontSize: 13,
    fontWeight: 600,
    color: 'var(--text-secondary)',
    margin: '0 0 8px 0',
  },
  stepsList: {
    margin: 0,
    paddingLeft: 20,
  },
  step: {
    fontSize: 13,
    color: 'var(--text-secondary)',
    marginBottom: 4,
    lineHeight: 1.5,
  },
  buttonRow: {
    display: 'flex',
    gap: 12,
    flexWrap: 'wrap',
  },
  primaryButton: {
    backgroundColor: 'var(--accent)',
    color: '#fff',
    border: 'none',
    borderRadius: 8,
    padding: '10px 16px',
    fontSize: 14,
    fontWeight: 500,
    cursor: 'pointer',
    transition: 'all 0.2s',
  },
  secondaryButton: {
    backgroundColor: 'transparent',
    color: 'var(--accent)',
    border: '1px solid var(--accent)',
    borderRadius: 8,
    padding: '10px 16px',
    fontSize: 14,
    fontWeight: 500,
    cursor: 'pointer',
    transition: 'all 0.2s',
  },
  grantedMessage: {
    display: 'flex',
    alignItems: 'center',
    gap: 8,
    color: '#34c759',
    fontSize: 14,
    fontWeight: 500,
  },
  restartWarning: {
    fontSize: 12,
    color: '#ff9500',
    marginTop: 12,
    marginBottom: 0,
  },
  footer: {
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'center',
    gap: 16,
    width: '100%',
  },
  continueButton: {
    backgroundColor: 'var(--accent)',
    color: '#fff',
    border: 'none',
    borderRadius: 10,
    padding: '14px 48px',
    fontSize: 16,
    fontWeight: 600,
    cursor: 'pointer',
    transition: 'all 0.2s',
    boxShadow: '0 4px 12px rgba(0, 122, 255, 0.3)',
  },
  pollingIndicator: {
    display: 'flex',
    alignItems: 'center',
    gap: 8,
    fontSize: 13,
    color: '#00d4ff',
  },
  pollingDot: {
    width: 8,
    height: 8,
    borderRadius: '50%',
    backgroundColor: '#00d4ff',
    animation: 'pulse 1s ease-in-out infinite',
  },
  restartNote: {
    fontSize: 12,
    color: '#ff9500',
    textAlign: 'center',
    marginTop: 16,
  },
  errorCard: {
    background: 'rgba(255, 59, 48, 0.1)',
    borderRadius: 12,
    padding: 16,
    border: '1px solid rgba(255, 59, 48, 0.3)',
    marginBottom: 16,
    width: '100%',
  },
  errorText: {
    color: '#ff6b6b',
    fontSize: 14,
    margin: 0,
  },
};

export default Permissions;
