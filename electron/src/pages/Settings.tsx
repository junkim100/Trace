import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import type { AllSettings, AppSettings, BlocklistEntry, InstalledApp } from '../types/trace-api';

export function Settings() {
  const navigate = useNavigate();
  const [settings, setSettings] = useState<AllSettings | null>(null);
  const [apiKey, setApiKey] = useState('');
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState<{ type: 'success' | 'error'; text: string } | null>(null);
  const [loading, setLoading] = useState(true);

  // Blocklist state
  const [blocklistEntries, setBlocklistEntries] = useState<BlocklistEntry[]>([]);
  const [blocklistLoading, setBlocklistLoading] = useState(false);
  const [newBlockType, setNewBlockType] = useState<'app' | 'domain'>('app');
  const [newBlockPattern, setNewBlockPattern] = useState('');
  const [newBlockName, setNewBlockName] = useState('');

  // Installed apps state (for app picker)
  const [installedApps, setInstalledApps] = useState<InstalledApp[]>([]);
  const [showAppPicker, setShowAppPicker] = useState(false);
  const [appSearchQuery, setAppSearchQuery] = useState('');

  // Blocklist section message (separate from global message)
  const [blocklistMessage, setBlocklistMessage] = useState<{ type: 'success' | 'error'; text: string } | null>(null);

  // App version
  const [appVersion, setAppVersion] = useState<string>('');

  // User profile state
  const [userProfile, setUserProfile] = useState({
    name: '',
    age: '',
    interests: '',
    languages: '',
    additional_info: '',
  });
  const [profileSaving, setProfileSaving] = useState(false);

  // Export state
  const [exportLoading, setExportLoading] = useState(false);
  const [exportSummary, setExportSummary] = useState<{
    notes_in_db: number;
    markdown_files: number;
    entities: number;
    edges: number;
  } | null>(null);

  // Update state
  const [updateChecking, setUpdateChecking] = useState(false);
  const [updateInfo, setUpdateInfo] = useState<{
    available: boolean;
    latestVersion?: string;
    currentVersion?: string;
    releaseUrl?: string;
    releaseNotes?: string;
  } | null>(null);

  const loadBlocklist = async () => {
    setBlocklistLoading(true);
    try {
      const result = await window.traceAPI.blocklist.list(true);
      if (result.success) {
        setBlocklistEntries(result.entries);
      }
    } catch (err) {
      console.error('Failed to load blocklist:', err);
    } finally {
      setBlocklistLoading(false);
    }
  };

  const loadInstalledApps = async () => {
    try {
      const result = await window.traceAPI.apps.list();
      if (result.success) {
        setInstalledApps(result.apps);
      }
    } catch (err) {
      console.error('Failed to load installed apps:', err);
    }
  };

  useEffect(() => {
    const loadSettings = async () => {
      try {
        const result = await window.traceAPI.settings.getAll();
        setSettings(result);
      } catch (err) {
        console.error('Failed to load all settings:', err);
        // Fallback to legacy get
        try {
          const legacyResult = await window.traceAPI.settings.get();
          // Map legacy result to new structure
          setSettings({
            config: {
              appearance: { show_in_dock: false, launch_at_login: true },
              capture: {
                summarization_interval_minutes: 60,
                daily_revision_hour: 3,
                blocked_apps: [],
                blocked_domains: [],
              },
              notifications: { weekly_digest_enabled: true, weekly_digest_day: 'sunday' },
              shortcuts: { open_trace: 'CommandOrControl+Shift+T' },
              data: { retention_months: null },
              api_key: null,
            },
            options: {
              summarization_intervals: [30, 60, 120, 240],
              daily_revision_hours: Array.from({ length: 24 }, (_, i) => i),
              weekly_digest_days: ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday'],
              retention_months: [null, 6, 12, 24],
            },
            has_api_key: (legacyResult as AppSettings).has_api_key,
            paths: {
              data_dir: (legacyResult as AppSettings).data_dir,
              notes_dir: (legacyResult as AppSettings).notes_dir,
              db_path: (legacyResult as AppSettings).db_path,
              cache_dir: (legacyResult as AppSettings).cache_dir,
            },
          });
        } catch (fallbackErr) {
          setMessage({ type: 'error', text: 'Failed to load settings' });
        }
      } finally {
        setLoading(false);
      }
    };

    loadSettings();
    loadBlocklist();
    loadExportSummary();
    loadInstalledApps();

    // Load app version
    window.traceAPI.getVersion().then(setAppVersion).catch(() => {});

    // Load user profile
    const loadUserProfile = async () => {
      try {
        const profile = await window.traceAPI.settings.get('user_profile') as {
          name?: string;
          age?: string;
          interests?: string;
          languages?: string;
          additional_info?: string;
        } | null;
        if (profile) {
          setUserProfile({
            name: profile.name || '',
            age: profile.age || '',
            interests: profile.interests || '',
            languages: profile.languages || '',
            additional_info: profile.additional_info || '',
          });
        }
      } catch (err) {
        console.error('Failed to load user profile:', err);
      }
    };
    loadUserProfile();
  }, []);

  const loadExportSummary = async () => {
    try {
      const result = await window.traceAPI.export.summary();
      if (result.success) {
        setExportSummary({
          notes_in_db: result.notes_in_db,
          markdown_files: result.markdown_files,
          entities: result.entities,
          edges: result.edges,
        });
      }
    } catch (err) {
      console.error('Failed to load export summary:', err);
    }
  };

  const handleProfileChange = (key: string, value: string) => {
    setUserProfile(prev => ({ ...prev, [key]: value }));
  };

  const handleSaveProfile = async () => {
    setProfileSaving(true);
    setMessage(null);
    try {
      for (const [key, value] of Object.entries(userProfile)) {
        await window.traceAPI.settings.setValue(`user_profile.${key}`, value);
      }
      setMessage({ type: 'success', text: 'Profile saved successfully' });
    } catch (err) {
      setMessage({ type: 'error', text: err instanceof Error ? err.message : 'Failed to save profile' });
    } finally {
      setProfileSaving(false);
    }
  };

  const handleSaveApiKey = async () => {
    if (!apiKey.trim()) return;

    setSaving(true);
    setMessage(null);
    try {
      await window.traceAPI.settings.setApiKey(apiKey.trim());
      setMessage({ type: 'success', text: 'API key saved successfully' });
      setApiKey('');
      // Refresh settings
      const result = await window.traceAPI.settings.getAll();
      setSettings(result);
    } catch (err) {
      setMessage({ type: 'error', text: err instanceof Error ? err.message : 'Failed to save API key' });
    } finally {
      setSaving(false);
    }
  };

  const handleClearApiKey = async () => {
    setMessage(null);
    try {
      await window.traceAPI.settings.setValue('api_key', null);
      setMessage({ type: 'success', text: 'API key cleared' });
      // Refresh settings
      const result = await window.traceAPI.settings.getAll();
      setSettings(result);
    } catch (err) {
      setMessage({ type: 'error', text: err instanceof Error ? err.message : 'Failed to clear API key' });
    }
  };

  const handleSettingChange = async (key: string, value: unknown) => {
    try {
      const result = await window.traceAPI.settings.setValue(key, value);
      if (result.success) {
        // Refresh settings
        const updated = await window.traceAPI.settings.getAll();
        setSettings(updated as AllSettings);

        // Apply appearance changes immediately
        if (key === 'appearance.show_in_dock') {
          await window.traceAPI.appearance.setDockVisibility(value as boolean);
        } else if (key === 'appearance.launch_at_login') {
          await window.traceAPI.appearance.setLaunchAtLogin(value as boolean);
        }
      }
    } catch (err) {
      setMessage({ type: 'error', text: err instanceof Error ? err.message : 'Failed to save setting' });
    }
  };

  const handleAddBlocklistEntry = async () => {
    if (!newBlockPattern.trim()) return;

    try {
      const result = newBlockType === 'app'
        ? await window.traceAPI.blocklist.addApp(newBlockPattern.trim(), newBlockName.trim() || null)
        : await window.traceAPI.blocklist.addDomain(newBlockPattern.trim(), newBlockName.trim() || null);

      if (result.success) {
        setMessage({ type: 'success', text: `Added ${newBlockType} to blocklist` });
        setNewBlockPattern('');
        setNewBlockName('');
        loadBlocklist();
      } else {
        setMessage({ type: 'error', text: result.error || 'Failed to add to blocklist' });
      }
    } catch (err) {
      setMessage({ type: 'error', text: err instanceof Error ? err.message : 'Failed to add to blocklist' });
    }
  };

  const handleRemoveBlocklistEntry = async (blocklistId: string) => {
    try {
      const result = await window.traceAPI.blocklist.remove(blocklistId);
      if (result.success) {
        loadBlocklist();
      }
    } catch (err) {
      console.error('Failed to remove blocklist entry:', err);
    }
  };

  const handleToggleBlocklistEntry = async (blocklistId: string, enabled: boolean) => {
    try {
      const result = await window.traceAPI.blocklist.setEnabled(blocklistId, enabled);
      if (result.success) {
        loadBlocklist();
      }
    } catch (err) {
      console.error('Failed to toggle blocklist entry:', err);
    }
  };

  const handleInitDefaults = async () => {
    try {
      const result = await window.traceAPI.blocklist.initDefaults();
      if (result.success) {
        setBlocklistMessage({ type: 'success', text: `Added ${result.added} default blocklist entries` });
        loadBlocklist();
      }
    } catch (err) {
      setBlocklistMessage({ type: 'error', text: err instanceof Error ? err.message : 'Failed to initialize defaults' });
    }
  };

  const handleExport = async () => {
    setExportLoading(true);
    setMessage(null);
    try {
      const result = await window.traceAPI.export.saveArchive();
      if (result.canceled) {
        // User cancelled the dialog
        return;
      }
      if (result.success) {
        setMessage({
          type: 'success',
          text: `Exported ${result.notes_count} notes to ${result.export_path}`,
        });
      } else {
        setMessage({ type: 'error', text: result.error || 'Export failed' });
      }
    } catch (err) {
      setMessage({ type: 'error', text: err instanceof Error ? err.message : 'Export failed' });
    } finally {
      setExportLoading(false);
    }
  };

  const handleCheckForUpdates = async () => {
    setUpdateChecking(true);
    setMessage(null);
    try {
      const result = await window.traceAPI.updates.check({ silent: false, force: true });
      if (result.error) {
        setMessage({ type: 'error', text: result.error });
      } else if (result.available && result.updateInfo) {
        setUpdateInfo({
          available: true,
          latestVersion: result.updateInfo.latestVersion,
          currentVersion: result.updateInfo.currentVersion,
          releaseUrl: result.updateInfo.releaseUrl,
          releaseNotes: result.updateInfo.releaseNotes,
        });
      } else {
        setUpdateInfo({
          available: false,
          currentVersion: result.currentVersion,
        });
        setMessage({ type: 'success', text: 'You are running the latest version.' });
      }
    } catch (err) {
      setMessage({ type: 'error', text: err instanceof Error ? err.message : 'Failed to check for updates' });
    } finally {
      setUpdateChecking(false);
    }
  };

  const handleOpenReleasePage = async (url: string) => {
    try {
      await window.traceAPI.updates.openReleasePage(url);
    } catch (err) {
      console.error('Failed to open release page:', err);
    }
  };

  const formatHour = (hour: number) => {
    if (hour === 0) return '12:00 AM';
    if (hour === 12) return '12:00 PM';
    if (hour < 12) return `${hour}:00 AM`;
    return `${hour - 12}:00 PM`;
  };

  const formatInterval = (minutes: number) => {
    if (minutes < 60) return `${minutes} minutes`;
    if (minutes === 60) return '1 hour';
    return `${minutes / 60} hours`;
  };

  const formatRetention = (months: number | null) => {
    if (months === null) return 'Forever';
    if (months === 12) return '1 year';
    if (months === 24) return '2 years';
    return `${months} months`;
  };

  if (loading) {
    return (
      <div style={styles.container}>
        <div className="titlebar" style={styles.titlebar} />
        <main style={styles.main}>
          <div style={styles.loading}>Loading settings...</div>
        </main>
      </div>
    );
  }

  return (
    <div style={styles.container}>
      <div className="titlebar" style={styles.titlebar} />
      <main style={styles.main}>
        <div style={styles.header}>
          <button onClick={() => navigate(-1)} style={styles.backButton}>
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M19 12H5" />
              <path d="M12 19l-7-7 7-7" />
            </svg>
            Back
          </button>
          <h1 style={styles.title}>Settings</h1>
        </div>

        {message && (
          <div style={{
            ...styles.message,
            ...(message.type === 'success' ? styles.messageSuccess : styles.messageError),
          }}>
            {message.text}
          </div>
        )}

        <section style={styles.section}>
          <h2 style={styles.sectionTitle}>API Configuration</h2>
          <div style={styles.field}>
            <label style={styles.label}>OpenAI API Key</label>
            <p style={styles.description}>
              Required for generating summaries and answering queries.
            </p>

            {/* Status indicator */}
            <div style={styles.apiKeyStatus}>
              {settings?.has_api_key ? (
                <>
                  <span style={styles.apiKeyStatusSet}>
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                      <path d="M20 6L9 17l-5-5" />
                    </svg>
                    API key is set
                  </span>
                  <button
                    onClick={handleClearApiKey}
                    style={styles.clearButton}
                    type="button"
                  >
                    Clear
                  </button>
                </>
              ) : (
                <span style={styles.apiKeyStatusNotSet}>
                  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                    <circle cx="12" cy="12" r="10" />
                    <line x1="12" y1="8" x2="12" y2="12" />
                    <line x1="12" y1="16" x2="12.01" y2="16" />
                  </svg>
                  No API key set
                </span>
              )}
            </div>

            {/* Input for new key */}
            <div style={styles.inputRow}>
              <input
                type="password"
                value={apiKey}
                onChange={(e) => setApiKey(e.target.value)}
                placeholder="Enter new API key (sk-...)"
                style={styles.input}
              />
              <button
                onClick={handleSaveApiKey}
                disabled={!apiKey.trim() || saving}
                style={{
                  ...styles.saveButton,
                  ...(!apiKey.trim() || saving ? styles.saveButtonDisabled : {}),
                }}
              >
                {saving ? 'Saving...' : 'Save'}
              </button>
            </div>
          </div>
        </section>

        <section style={styles.section}>
          <h2 style={styles.sectionTitle}>Your Profile</h2>
          <p style={styles.description}>
            This information helps personalize your activity notes.
          </p>
          <div style={styles.field}>
            <label style={styles.label}>Name</label>
            <input
              type="text"
              value={userProfile.name}
              onChange={(e) => handleProfileChange('name', e.target.value)}
              placeholder="e.g., Alex Chen"
              style={styles.profileInput}
            />
          </div>
          <div style={styles.field}>
            <label style={styles.label}>Age</label>
            <input
              type="text"
              value={userProfile.age}
              onChange={(e) => handleProfileChange('age', e.target.value)}
              placeholder="e.g., 28"
              style={styles.profileInput}
            />
          </div>
          <div style={styles.field}>
            <label style={styles.label}>Interests & Hobbies</label>
            <textarea
              value={userProfile.interests}
              onChange={(e) => handleProfileChange('interests', e.target.value)}
              placeholder="e.g., software development, photography, hiking, cooking"
              style={styles.profileTextarea}
            />
          </div>
          <div style={styles.field}>
            <label style={styles.label}>Languages You Speak</label>
            <input
              type="text"
              value={userProfile.languages}
              onChange={(e) => handleProfileChange('languages', e.target.value)}
              placeholder="e.g., English, Spanish, Mandarin"
              style={styles.profileInput}
            />
          </div>
          <div style={styles.field}>
            <label style={styles.label}>Additional Info</label>
            <textarea
              value={userProfile.additional_info}
              onChange={(e) => handleProfileChange('additional_info', e.target.value)}
              placeholder="e.g., I work as a product manager at a tech startup, prefer working late at night"
              style={styles.profileTextarea}
            />
          </div>
          <button
            onClick={handleSaveProfile}
            disabled={profileSaving}
            style={{
              ...styles.saveButton,
              ...(profileSaving ? styles.saveButtonDisabled : {}),
            }}
          >
            {profileSaving ? 'Saving...' : 'Save Profile'}
          </button>
        </section>

        <section style={styles.section}>
          <h2 style={styles.sectionTitle}>Appearance</h2>
          <div style={styles.field}>
            <div style={styles.toggleRow}>
              <div>
                <label style={styles.label}>Show in Dock</label>
                <p style={styles.description}>When off, Trace only appears in the menu bar.</p>
              </div>
              <label className="settings-switch" style={styles.switch}>
                <input
                  type="checkbox"
                  checked={settings?.config.appearance.show_in_dock ?? false}
                  onChange={(e) => handleSettingChange('appearance.show_in_dock', e.target.checked)}
                />
                <span style={styles.switchSlider}></span>
              </label>
            </div>
          </div>
          <div style={styles.field}>
            <div style={styles.toggleRow}>
              <div>
                <label style={styles.label}>Launch at Login</label>
                <p style={styles.description}>Start Trace automatically when you log in.</p>
              </div>
              <label className="settings-switch" style={styles.switch}>
                <input
                  type="checkbox"
                  checked={settings?.config.appearance.launch_at_login ?? true}
                  onChange={(e) => handleSettingChange('appearance.launch_at_login', e.target.checked)}
                />
                <span style={styles.switchSlider}></span>
              </label>
            </div>
          </div>
        </section>

        <section style={styles.section}>
          <h2 style={styles.sectionTitle}>Capture & Processing</h2>

          {/* Power Saving Mode */}
          <div style={styles.field}>
            <label style={styles.label}>Power Saving Mode</label>
            <p style={styles.description}>
              Reduce capture frequency to conserve battery. Normal capture: every 1 second.
            </p>
            <select
              value={settings?.config.capture.power_saving_mode ?? 'automatic'}
              onChange={(e) => handleSettingChange('capture.power_saving_mode', e.target.value)}
              style={styles.select}
            >
              <option value="off">Off - Always capture at normal speed</option>
              <option value="automatic">Automatic - Activate when battery is low</option>
              <option value="always_on">Always On - Always reduce capture on battery</option>
            </select>

            {/* Battery threshold setting for automatic mode */}
            {settings?.config.capture.power_saving_mode === 'automatic' && (
              <div style={styles.powerSavingOptions}>
                <label style={styles.subLabel}>Activate when battery is below:</label>
                <div style={styles.sliderRow}>
                  <input
                    type="range"
                    min="10"
                    max="50"
                    step="5"
                    value={settings?.config.capture.power_saving_threshold ?? 20}
                    onChange={(e) => handleSettingChange('capture.power_saving_threshold', Number(e.target.value))}
                    style={styles.slider}
                  />
                  <span style={styles.sliderValue}>{settings?.config.capture.power_saving_threshold ?? 20}%</span>
                </div>
              </div>
            )}

            {/* Capture interval when power saving is active */}
            {settings?.config.capture.power_saving_mode !== 'off' && (
              <div style={styles.powerSavingOptions}>
                <label style={styles.subLabel}>Capture interval when power saving:</label>
                <select
                  value={settings?.config.capture.power_saving_interval ?? 5}
                  onChange={(e) => handleSettingChange('capture.power_saving_interval', Number(e.target.value))}
                  style={{ ...styles.select, marginTop: '0.5rem' }}
                >
                  <option value={3}>Every 3 seconds (mild saving)</option>
                  <option value={5}>Every 5 seconds (recommended)</option>
                  <option value={10}>Every 10 seconds (moderate saving)</option>
                  <option value={30}>Every 30 seconds (aggressive saving)</option>
                </select>
              </div>
            )}

            {/* Info box showing current behavior */}
            <div style={styles.infoBox}>
              <span style={styles.infoIcon}>ℹ</span>
              <span>
                {settings?.config.capture.power_saving_mode === 'off'
                  ? 'Captures every 1 second regardless of power source.'
                  : settings?.config.capture.power_saving_mode === 'always_on'
                  ? `On battery: captures every ${settings?.config.capture.power_saving_interval ?? 5}s. On power: every 1s.`
                  : `On battery below ${settings?.config.capture.power_saving_threshold ?? 20}%: captures every ${settings?.config.capture.power_saving_interval ?? 5}s. Otherwise: every 1s.`}
              </span>
            </div>
          </div>

          <div style={styles.field}>
            <label style={styles.label}>Summarization Interval</label>
            <p style={styles.description}>How often to generate summary notes from captured screenshots.</p>
            <select
              value={settings?.config.capture.summarization_interval_minutes ?? 60}
              onChange={(e) => handleSettingChange('capture.summarization_interval_minutes', Number(e.target.value))}
              style={styles.select}
            >
              {settings?.options.summarization_intervals.map((interval) => (
                <option key={interval} value={interval}>
                  {formatInterval(interval)}
                </option>
              ))}
            </select>
          </div>

          <div style={styles.field}>
            <label style={styles.label}>Daily Revision Time</label>
            <p style={styles.description}>When to run daily processing (revision, cleanup).</p>
            <select
              value={settings?.config.capture.daily_revision_hour ?? 3}
              onChange={(e) => handleSettingChange('capture.daily_revision_hour', Number(e.target.value))}
              style={styles.select}
            >
              {settings?.options.daily_revision_hours.map((hour) => (
                <option key={hour} value={hour}>
                  {formatHour(hour)}
                </option>
              ))}
            </select>
          </div>

          {/* Screenshot Quality with better explanation */}
          <div style={styles.field}>
            <label style={styles.label}>Screenshot Quality</label>
            <p style={styles.description}>
              JPEG compression quality. Higher values produce clearer screenshots but use more storage.
            </p>
            <div style={styles.sliderContainer}>
              <div style={styles.sliderLabels}>
                <span style={styles.sliderLabelLeft}>Smaller files</span>
                <span style={styles.sliderLabelRight}>Better quality</span>
              </div>
              <div style={styles.sliderRow}>
                <input
                  type="range"
                  min="50"
                  max="100"
                  step="5"
                  value={settings?.config.capture.jpeg_quality ?? 85}
                  onChange={(e) => handleSettingChange('capture.jpeg_quality', Number(e.target.value))}
                  style={styles.slider}
                />
                <span style={styles.sliderValue}>{settings?.config.capture.jpeg_quality ?? 85}%</span>
              </div>
              <div style={styles.sliderHint}>
                {(settings?.config.capture.jpeg_quality ?? 85) <= 60
                  ? '⚠️ Low quality - text may be hard to read'
                  : (settings?.config.capture.jpeg_quality ?? 85) <= 75
                  ? 'Good balance of quality and file size'
                  : (settings?.config.capture.jpeg_quality ?? 85) <= 90
                  ? '✓ Recommended - clear screenshots'
                  : '✓ Maximum quality - larger files'}
              </div>
            </div>
          </div>

          {/* Deduplication Sensitivity with better explanation */}
          <div style={styles.field}>
            <label style={styles.label}>Deduplication Sensitivity</label>
            <p style={styles.description}>
              Controls how similar two screenshots must be to skip the duplicate.
              Lower values require more similarity (stricter), higher values allow more differences (looser).
            </p>
            <div style={styles.sliderContainer}>
              <div style={styles.sliderLabels}>
                <span style={styles.sliderLabelLeft}>Stricter (keep more)</span>
                <span style={styles.sliderLabelRight}>Looser (skip more)</span>
              </div>
              <div style={styles.sliderRow}>
                <input
                  type="range"
                  min="1"
                  max="15"
                  step="1"
                  value={settings?.config.capture.dedup_threshold ?? 5}
                  onChange={(e) => handleSettingChange('capture.dedup_threshold', Number(e.target.value))}
                  style={styles.slider}
                />
                <span style={styles.sliderValue}>{settings?.config.capture.dedup_threshold ?? 5}</span>
              </div>
              <div style={styles.sliderHint}>
                {(settings?.config.capture.dedup_threshold ?? 5) <= 3
                  ? 'Very strict - keeps most screenshots, uses more storage'
                  : (settings?.config.capture.dedup_threshold ?? 5) <= 6
                  ? '✓ Recommended - good balance'
                  : (settings?.config.capture.dedup_threshold ?? 5) <= 10
                  ? 'Moderate - skips similar content, saves storage'
                  : '⚠️ Very loose - may skip important changes'}
              </div>
            </div>
          </div>
        </section>

        <section style={styles.section}>
          <h2 style={styles.sectionTitle}>AI Models</h2>
          <p style={styles.description}>
            Select which OpenAI models to use for different tasks. Faster models use less API credits.
          </p>
          <div style={styles.field}>
            <label style={styles.label}>Frame Triage</label>
            <p style={styles.description}>Fast model for analyzing screenshots and selecting keyframes.</p>
            <select
              value={settings?.config.models?.triage ?? 'gpt-5-nano-2025-08-07'}
              onChange={(e) => handleSettingChange('models.triage', e.target.value)}
              style={styles.select}
            >
              <option value="gpt-5-nano-2025-08-07">GPT-5 Nano (Fastest)</option>
              <option value="gpt-4o-mini">GPT-4o Mini</option>
            </select>
          </div>
          <div style={styles.field}>
            <label style={styles.label}>Hourly Summarization</label>
            <p style={styles.description}>Model for generating hourly summary notes.</p>
            <select
              value={settings?.config.models?.hourly ?? 'gpt-5-mini-2025-08-07'}
              onChange={(e) => handleSettingChange('models.hourly', e.target.value)}
              style={styles.select}
            >
              <option value="gpt-5-mini-2025-08-07">GPT-5 Mini (Recommended)</option>
              <option value="gpt-4o-mini">GPT-4o Mini</option>
              <option value="gpt-4o">GPT-4o (More detailed)</option>
            </select>
          </div>
          <div style={styles.field}>
            <label style={styles.label}>Daily Revision</label>
            <p style={styles.description}>Full-featured model for daily note revision and entity extraction.</p>
            <select
              value={settings?.config.models?.daily ?? 'gpt-5.2-2025-12-11'}
              onChange={(e) => handleSettingChange('models.daily', e.target.value)}
              style={styles.select}
            >
              <option value="gpt-5.2-2025-12-11">GPT-5.2 (Best quality)</option>
              <option value="gpt-4o">GPT-4o</option>
              <option value="gpt-5-mini-2025-08-07">GPT-5 Mini (Faster)</option>
            </select>
          </div>
          <div style={styles.field}>
            <label style={styles.label}>Chat Responses</label>
            <p style={styles.description}>Model for answering your questions about past activity.</p>
            <select
              value={settings?.config.models?.chat ?? 'gpt-5-mini-2025-08-07'}
              onChange={(e) => handleSettingChange('models.chat', e.target.value)}
              style={styles.select}
            >
              <option value="gpt-5-mini-2025-08-07">GPT-5 Mini (Recommended)</option>
              <option value="gpt-4o-mini">GPT-4o Mini (Faster)</option>
              <option value="gpt-4o">GPT-4o (More detailed)</option>
            </select>
          </div>
        </section>

        <section style={styles.section}>
          <h2 style={styles.sectionTitle}>Notifications</h2>
          <div style={styles.field}>
            <div style={styles.toggleRow}>
              <div>
                <label style={styles.label}>Weekly Digest</label>
                <p style={styles.description}>Receive a weekly summary notification.</p>
              </div>
              <label className="settings-switch" style={styles.switch}>
                <input
                  type="checkbox"
                  checked={settings?.config.notifications.weekly_digest_enabled ?? true}
                  onChange={(e) => handleSettingChange('notifications.weekly_digest_enabled', e.target.checked)}
                />
                <span style={styles.switchSlider}></span>
              </label>
            </div>
          </div>
          {settings?.config.notifications.weekly_digest_enabled && (
            <div style={styles.field}>
              <label style={styles.label}>Digest Day</label>
              <p style={styles.description}>Day of the week to send the weekly digest.</p>
              <select
                value={settings?.config.notifications.weekly_digest_day ?? 'sunday'}
                onChange={(e) => handleSettingChange('notifications.weekly_digest_day', e.target.value)}
                style={styles.select}
              >
                {settings?.options.weekly_digest_days.map((day) => (
                  <option key={day} value={day}>
                    {day.charAt(0).toUpperCase() + day.slice(1)}
                  </option>
                ))}
              </select>
            </div>
          )}
        </section>

        <section style={styles.section}>
          <h2 style={styles.sectionTitle}>Keyboard Shortcuts</h2>
          <div style={styles.field}>
            <label style={styles.label}>Open Trace</label>
            <p style={styles.description}>Global shortcut to show/hide the Trace window.</p>
            <div style={styles.shortcutDisplay}>
              {settings?.config.shortcuts.open_trace?.replace('CommandOrControl', '⌘').replace('+', ' + ') ?? '⌘ + Shift + T'}
            </div>
          </div>
          <div style={styles.field}>
            <label style={styles.label}>Open Settings</label>
            <p style={styles.description}>Open settings from anywhere in the app.</p>
            <div style={styles.shortcutDisplay}>⌘ + ,</div>
          </div>
        </section>

        <section style={styles.section}>
          <h2 style={styles.sectionTitle}>Data Management</h2>
          <div style={styles.field}>
            <label style={styles.label}>Data Retention</label>
            <p style={styles.description}>How long to keep notes and data. Older data will be automatically deleted.</p>
            <select
              value={settings?.config.data.retention_months ?? ''}
              onChange={(e) => handleSettingChange('data.retention_months', e.target.value === '' ? null : Number(e.target.value))}
              style={styles.select}
            >
              {settings?.options.retention_months.map((months) => (
                <option key={months ?? 'forever'} value={months ?? ''}>
                  {formatRetention(months)}
                </option>
              ))}
            </select>
          </div>
        </section>

        <section style={styles.section}>
          <h2 style={styles.sectionTitle}>Privacy Blocklist</h2>

          {blocklistMessage && (
            <div style={{
              ...styles.message,
              ...(blocklistMessage.type === 'success' ? styles.messageSuccess : styles.messageError),
              marginBottom: '1rem',
            }}>
              {blocklistMessage.text}
            </div>
          )}

          <p style={styles.description}>
            Block specific apps and websites from being captured.
            Use this to protect sensitive activities like banking, medical, or password managers.
          </p>

          {/* Tab selector for Apps vs Domains */}
          <div style={styles.tabContainer}>
            <button
              style={{
                ...styles.tab,
                ...(newBlockType === 'app' ? styles.tabActive : {}),
              }}
              onClick={() => setNewBlockType('app')}
            >
              Block Apps
            </button>
            <button
              style={{
                ...styles.tab,
                ...(newBlockType === 'domain' ? styles.tabActive : {}),
              }}
              onClick={() => setNewBlockType('domain')}
            >
              Block Websites
            </button>
          </div>

          {/* App picker */}
          {newBlockType === 'app' && (
            <div style={styles.blocklistAddSection}>
              <button
                onClick={() => setShowAppPicker(!showAppPicker)}
                style={styles.appPickerButton}
              >
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <line x1="12" y1="5" x2="12" y2="19" />
                  <line x1="5" y1="12" x2="19" y2="12" />
                </svg>
                Add Application to Blocklist
              </button>

              {showAppPicker && (
                <div style={styles.appPickerDropdown}>
                  <input
                    type="text"
                    value={appSearchQuery}
                    onChange={(e) => setAppSearchQuery(e.target.value)}
                    placeholder="Search installed apps..."
                    style={styles.appSearchInput}
                    autoFocus
                  />
                  <div style={styles.appList}>
                    {installedApps
                      .filter(app =>
                        app.name.toLowerCase().includes(appSearchQuery.toLowerCase()) ||
                        app.bundleId.toLowerCase().includes(appSearchQuery.toLowerCase())
                      )
                      .slice(0, 20)
                      .map((app) => {
                        const isBlocked = blocklistEntries.some(
                          (e) => e.block_type === 'app' && e.pattern === app.bundleId
                        );
                        return (
                          <button
                            key={app.bundleId}
                            style={{
                              ...styles.appItem,
                              ...(isBlocked ? styles.appItemDisabled : {}),
                            }}
                            onClick={async () => {
                              if (isBlocked) return;
                              try {
                                const result = await window.traceAPI.blocklist.addApp(
                                  app.bundleId,
                                  app.name
                                );
                                if (result.success) {
                                  setMessage({ type: 'success', text: `Blocked ${app.name}` });
                                  loadBlocklist();
                                  setShowAppPicker(false);
                                  setAppSearchQuery('');
                                }
                              } catch (err) {
                                setMessage({ type: 'error', text: 'Failed to add app' });
                              }
                            }}
                            disabled={isBlocked}
                          >
                            <span style={styles.appItemName}>{app.name}</span>
                            <span style={styles.appItemBundleId}>{app.bundleId}</span>
                            {isBlocked && <span style={styles.appItemBlocked}>Already blocked</span>}
                          </button>
                        );
                      })}
                    {installedApps.filter(app =>
                      app.name.toLowerCase().includes(appSearchQuery.toLowerCase()) ||
                      app.bundleId.toLowerCase().includes(appSearchQuery.toLowerCase())
                    ).length === 0 && (
                      <div style={styles.appListEmpty}>
                        No apps found matching &quot;{appSearchQuery}&quot;
                      </div>
                    )}
                  </div>
                </div>
              )}
            </div>
          )}

          {/* Domain input */}
          {newBlockType === 'domain' && (
            <div style={styles.domainInputSection}>
              <div style={styles.domainInputRow}>
                <input
                  type="text"
                  value={newBlockPattern}
                  onChange={(e) => setNewBlockPattern(e.target.value)}
                  placeholder="Enter domain (e.g., bankofamerica.com)"
                  style={styles.domainInput}
                  onKeyPress={(e) => {
                    if (e.key === 'Enter' && newBlockPattern.trim()) {
                      handleAddBlocklistEntry();
                    }
                  }}
                />
                <button
                  onClick={handleAddBlocklistEntry}
                  disabled={!newBlockPattern.trim()}
                  style={{
                    ...styles.addDomainButton,
                    ...(!newBlockPattern.trim() ? styles.saveButtonDisabled : {}),
                  }}
                >
                  Add Domain
                </button>
              </div>
              <p style={styles.domainHint}>
                Blocks all pages on this domain and its subdomains
              </p>
            </div>
          )}

          {/* Initialize defaults button */}
          {blocklistEntries.length === 0 && (
            <button
              onClick={handleInitDefaults}
              style={styles.initDefaultsButton}
            >
              Add Recommended Defaults (Banking, Password Managers)
            </button>
          )}

          {/* Blocklist entries */}
          {blocklistLoading ? (
            <div style={styles.loading}>Loading blocklist...</div>
          ) : blocklistEntries.length === 0 ? (
            <p style={styles.emptyState}>No blocked apps or domains yet.</p>
          ) : (
            <div style={styles.blocklistEntries}>
              {blocklistEntries.map((entry) => (
                <div key={entry.blocklist_id} style={styles.blocklistEntry}>
                  <div style={styles.entryInfo}>
                    <span style={styles.entryType}>{entry.block_type}</span>
                    <span style={styles.entryPattern}>
                      {entry.display_name || entry.pattern}
                    </span>
                    {entry.display_name && (
                      <span style={styles.entryPatternSub}>{entry.pattern}</span>
                    )}
                  </div>
                  <div style={styles.entryActions}>
                    <button
                      onClick={() => handleToggleBlocklistEntry(entry.blocklist_id, !entry.enabled)}
                      style={{
                        ...styles.toggleButton,
                        ...(entry.enabled ? styles.toggleEnabled : styles.toggleDisabled),
                      }}
                    >
                      {entry.enabled ? 'Enabled' : 'Disabled'}
                    </button>
                    <button
                      onClick={() => handleRemoveBlocklistEntry(entry.blocklist_id)}
                      style={styles.removeButton}
                    >
                      Remove
                    </button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </section>

        <section style={styles.section}>
          <h2 style={styles.sectionTitle}>Export & Backup</h2>
          <p style={styles.description}>
            Export your data as a ZIP archive containing all notes, entities, and relationships.
          </p>

          {exportSummary && (
            <div style={styles.exportSummary}>
              <div style={styles.summaryItem}>
                <span style={styles.summaryLabel}>Notes</span>
                <span style={styles.summaryValue}>{exportSummary.notes_in_db}</span>
              </div>
              <div style={styles.summaryItem}>
                <span style={styles.summaryLabel}>Markdown Files</span>
                <span style={styles.summaryValue}>{exportSummary.markdown_files}</span>
              </div>
              <div style={styles.summaryItem}>
                <span style={styles.summaryLabel}>Entities</span>
                <span style={styles.summaryValue}>{exportSummary.entities}</span>
              </div>
              <div style={styles.summaryItem}>
                <span style={styles.summaryLabel}>Relationships</span>
                <span style={styles.summaryValue}>{exportSummary.edges}</span>
              </div>
            </div>
          )}

          <button
            onClick={handleExport}
            disabled={exportLoading}
            style={{
              ...styles.exportButton,
              ...(exportLoading ? styles.saveButtonDisabled : {}),
            }}
          >
            {exportLoading ? 'Exporting...' : 'Export to ZIP Archive'}
          </button>
        </section>

        <section style={styles.section}>
          <h2 style={styles.sectionTitle}>Updates</h2>
          <div style={styles.field}>
            <div style={styles.toggleRow}>
              <div>
                <label style={styles.label}>Check for Updates on Launch</label>
                <p style={styles.description}>Automatically check for updates when Trace starts.</p>
              </div>
              <label className="settings-switch" style={styles.switch}>
                <input
                  type="checkbox"
                  checked={settings?.config.updates?.check_on_launch ?? true}
                  onChange={(e) => handleSettingChange('updates.check_on_launch', e.target.checked)}
                />
                <span style={styles.switchSlider}></span>
              </label>
            </div>
          </div>
          <div style={styles.field}>
            <div style={styles.toggleRow}>
              <div>
                <label style={styles.label}>Check Periodically</label>
                <p style={styles.description}>Check for updates in the background every 24 hours.</p>
              </div>
              <label className="settings-switch" style={styles.switch}>
                <input
                  type="checkbox"
                  checked={settings?.config.updates?.check_periodically ?? true}
                  onChange={(e) => handleSettingChange('updates.check_periodically', e.target.checked)}
                />
                <span style={styles.switchSlider}></span>
              </label>
            </div>
          </div>

          {updateInfo?.available && (
            <div style={styles.updateAvailable}>
              <div style={styles.updateAvailableHeader}>
                <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <circle cx="12" cy="12" r="10" />
                  <line x1="12" y1="8" x2="12" y2="12" />
                  <line x1="12" y1="16" x2="12.01" y2="16" />
                </svg>
                <span>Update Available: v{updateInfo.latestVersion}</span>
              </div>
              {updateInfo.releaseNotes && (
                <p style={styles.updateNotes}>{updateInfo.releaseNotes}</p>
              )}
              <button
                onClick={() => updateInfo.releaseUrl && handleOpenReleasePage(updateInfo.releaseUrl)}
                style={styles.downloadButton}
              >
                Download Update
              </button>
            </div>
          )}

          <button
            onClick={handleCheckForUpdates}
            disabled={updateChecking}
            style={{
              ...styles.checkUpdateButton,
              ...(updateChecking ? styles.saveButtonDisabled : {}),
            }}
          >
            {updateChecking ? 'Checking...' : 'Check for Updates Now'}
          </button>
        </section>

        <section style={styles.section}>
          <h2 style={styles.sectionTitle}>About</h2>
          <div style={styles.field}>
            <p style={styles.aboutText}>
              Trace is a macOS app that captures your digital activity,
              generates Markdown notes, builds a relationship graph,
              and provides time-aware chat and search.
            </p>
          </div>
          {appVersion && (
            <div style={styles.versionInfo}>
              Version {appVersion}
            </div>
          )}
        </section>
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
  titlebar: {
    minHeight: '36px',
  },
  main: {
    flex: 1,
    padding: '2rem',
    maxWidth: '600px',
    width: '100%',
    margin: '0 auto',
    overflowY: 'auto',
  },
  header: {
    display: 'flex',
    alignItems: 'center',
    gap: '1rem',
    marginBottom: '2rem',
  },
  backButton: {
    display: 'flex',
    alignItems: 'center',
    gap: '0.5rem',
    backgroundColor: 'transparent',
    border: 'none',
    color: 'var(--accent)',
    fontSize: '0.9rem',
    cursor: 'pointer',
    padding: '0.5rem',
    borderRadius: '6px',
  },
  title: {
    fontSize: '1.5rem',
    fontWeight: 600,
    color: 'var(--text-primary)',
  },
  loading: {
    display: 'flex',
    justifyContent: 'center',
    alignItems: 'center',
    height: '200px',
    color: 'var(--text-secondary)',
  },
  message: {
    padding: '0.75rem 1rem',
    borderRadius: '8px',
    marginBottom: '1.5rem',
    fontSize: '0.9rem',
  },
  messageSuccess: {
    backgroundColor: 'rgba(52, 199, 89, 0.15)',
    border: '1px solid rgba(52, 199, 89, 0.3)',
    color: '#34c759',
  },
  messageError: {
    backgroundColor: 'rgba(255, 59, 48, 0.15)',
    border: '1px solid rgba(255, 59, 48, 0.3)',
    color: '#ff3b30',
  },
  section: {
    marginBottom: '2rem',
  },
  sectionTitle: {
    fontSize: '0.875rem',
    fontWeight: 600,
    color: 'var(--text-secondary)',
    textTransform: 'uppercase',
    letterSpacing: '0.05em',
    marginBottom: '1rem',
  },
  field: {
    marginBottom: '1rem',
  },
  label: {
    display: 'block',
    fontSize: '0.95rem',
    fontWeight: 500,
    color: 'var(--text-primary)',
    marginBottom: '0.25rem',
  },
  description: {
    fontSize: '0.85rem',
    color: 'var(--text-secondary)',
    marginBottom: '0.75rem',
  },
  status: {
    color: '#34c759',
    fontWeight: 500,
  },
  inputRow: {
    display: 'flex',
    gap: '0.5rem',
  },
  input: {
    flex: 1,
    backgroundColor: 'var(--bg-secondary)',
    border: '1px solid var(--border)',
    borderRadius: '8px',
    padding: '0.625rem 0.875rem',
    fontSize: '0.9rem',
    color: 'var(--text-primary)',
    outline: 'none',
  },
  toggleButton: {
    backgroundColor: 'var(--bg-secondary)',
    border: '1px solid var(--border)',
    borderRadius: '8px',
    padding: '0.625rem 0.875rem',
    fontSize: '0.85rem',
    color: 'var(--text-secondary)',
    cursor: 'pointer',
  },
  saveButton: {
    backgroundColor: 'var(--accent)',
    border: 'none',
    borderRadius: '8px',
    padding: '0.625rem 1.25rem',
    fontSize: '0.9rem',
    fontWeight: 500,
    color: 'white',
    cursor: 'pointer',
  },
  saveButtonDisabled: {
    backgroundColor: '#404040',
    cursor: 'not-allowed',
    opacity: 0.5,
  },
  aboutText: {
    fontSize: '0.9rem',
    color: 'var(--text-secondary)',
    lineHeight: 1.6,
  },
  // Toggle switch styles
  toggleRow: {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'flex-start',
    gap: '1rem',
  },
  switch: {
    position: 'relative',
    display: 'inline-block',
    width: '44px',
    height: '24px',
    flexShrink: 0,
  },
  switchSlider: {
    position: 'absolute',
    cursor: 'pointer',
    top: 0,
    left: 0,
    right: 0,
    bottom: 0,
    backgroundColor: 'var(--bg-secondary)',
    border: '1px solid var(--border)',
    transition: '.2s',
    borderRadius: '24px',
  },
  // Select styles
  select: {
    backgroundColor: 'var(--bg-secondary)',
    border: '1px solid var(--border)',
    borderRadius: '8px',
    padding: '0.625rem 0.875rem',
    fontSize: '0.9rem',
    color: 'var(--text-primary)',
    outline: 'none',
    cursor: 'pointer',
    minWidth: '200px',
    WebkitAppearance: 'menulist',
  },
  // Slider styles
  sliderRow: {
    display: 'flex',
    alignItems: 'center',
    gap: '1rem',
  },
  slider: {
    flex: 1,
    height: '4px',
    backgroundColor: 'var(--border)',
    borderRadius: '2px',
    appearance: 'none' as const,
    cursor: 'pointer',
  },
  sliderValue: {
    minWidth: '40px',
    textAlign: 'right' as const,
    fontSize: '0.9rem',
    fontWeight: 500,
    color: 'var(--text-primary)',
    fontFamily: 'ui-monospace, SFMono-Regular, SF Mono, Menlo, monospace',
  },
  // Shortcut display
  shortcutDisplay: {
    display: 'inline-block',
    backgroundColor: 'var(--bg-secondary)',
    border: '1px solid var(--border)',
    borderRadius: '6px',
    padding: '0.5rem 0.75rem',
    fontSize: '0.9rem',
    fontFamily: 'ui-monospace, SFMono-Regular, SF Mono, Menlo, monospace',
    color: 'var(--text-primary)',
  },
  // Blocklist styles
  tabContainer: {
    display: 'flex',
    gap: '0.5rem',
    marginBottom: '1rem',
  },
  tab: {
    flex: 1,
    padding: '0.75rem 1rem',
    backgroundColor: 'var(--bg-secondary)',
    border: '1px solid var(--border)',
    borderRadius: '8px',
    fontSize: '0.9rem',
    fontWeight: 500,
    color: 'var(--text-secondary)',
    cursor: 'pointer',
    transition: 'all 0.2s ease',
  },
  tabActive: {
    backgroundColor: 'var(--accent)',
    borderColor: 'var(--accent)',
    color: 'white',
  },
  blocklistAddSection: {
    marginBottom: '1rem',
  },
  appPickerButton: {
    display: 'flex',
    alignItems: 'center',
    gap: '0.5rem',
    width: '100%',
    padding: '0.875rem 1rem',
    backgroundColor: 'var(--bg-secondary)',
    border: '1px dashed var(--border)',
    borderRadius: '8px',
    fontSize: '0.9rem',
    color: 'var(--text-primary)',
    cursor: 'pointer',
    transition: 'all 0.2s ease',
  },
  appPickerDropdown: {
    marginTop: '0.5rem',
    backgroundColor: 'var(--bg-secondary)',
    border: '1px solid var(--border)',
    borderRadius: '8px',
    overflow: 'hidden',
  },
  appSearchInput: {
    width: '100%',
    padding: '0.75rem 1rem',
    backgroundColor: 'transparent',
    border: 'none',
    borderBottom: '1px solid var(--border)',
    fontSize: '0.9rem',
    color: 'var(--text-primary)',
    outline: 'none',
  },
  appList: {
    maxHeight: '300px',
    overflowY: 'auto',
  },
  appItem: {
    display: 'flex',
    flexDirection: 'column' as const,
    alignItems: 'flex-start',
    width: '100%',
    padding: '0.75rem 1rem',
    backgroundColor: 'transparent',
    border: 'none',
    borderBottom: '1px solid var(--border)',
    cursor: 'pointer',
    textAlign: 'left' as const,
    transition: 'background-color 0.15s ease',
  },
  appItemDisabled: {
    opacity: 0.5,
    cursor: 'not-allowed',
  },
  appItemName: {
    fontSize: '0.9rem',
    fontWeight: 500,
    color: 'var(--text-primary)',
  },
  appItemBundleId: {
    fontSize: '0.75rem',
    color: 'var(--text-secondary)',
    fontFamily: 'ui-monospace, SFMono-Regular, SF Mono, Menlo, monospace',
  },
  appItemBlocked: {
    fontSize: '0.75rem',
    color: '#34c759',
    marginTop: '0.25rem',
  },
  appListEmpty: {
    padding: '1rem',
    textAlign: 'center' as const,
    color: 'var(--text-secondary)',
    fontSize: '0.85rem',
  },
  domainInputSection: {
    marginBottom: '1rem',
  },
  domainInputRow: {
    display: 'flex',
    gap: '0.5rem',
  },
  domainInput: {
    flex: 1,
    padding: '0.75rem 1rem',
    backgroundColor: 'var(--bg-secondary)',
    border: '1px solid var(--border)',
    borderRadius: '8px',
    fontSize: '0.9rem',
    color: 'var(--text-primary)',
    outline: 'none',
  },
  addDomainButton: {
    padding: '0.75rem 1.25rem',
    backgroundColor: 'var(--accent)',
    border: 'none',
    borderRadius: '8px',
    fontSize: '0.9rem',
    fontWeight: 500,
    color: 'white',
    cursor: 'pointer',
    whiteSpace: 'nowrap' as const,
  },
  domainHint: {
    fontSize: '0.8rem',
    color: 'var(--text-secondary)',
    marginTop: '0.5rem',
  },
  initDefaultsButton: {
    backgroundColor: 'transparent',
    border: '1px solid var(--border)',
    borderRadius: '8px',
    padding: '0.75rem 1rem',
    fontSize: '0.85rem',
    color: 'var(--text-secondary)',
    cursor: 'pointer',
    marginBottom: '1rem',
    width: '100%',
    textAlign: 'center' as const,
  },
  emptyState: {
    fontSize: '0.85rem',
    color: 'var(--text-secondary)',
    fontStyle: 'italic',
  },
  blocklistEntries: {
    display: 'flex',
    flexDirection: 'column',
    gap: '0.5rem',
  },
  blocklistEntry: {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
    backgroundColor: 'var(--bg-secondary)',
    border: '1px solid var(--border)',
    borderRadius: '8px',
    padding: '0.75rem 1rem',
  },
  entryInfo: {
    display: 'flex',
    alignItems: 'center',
    gap: '0.5rem',
    flexWrap: 'wrap',
    flex: 1,
  },
  entryType: {
    fontSize: '0.7rem',
    fontWeight: 600,
    textTransform: 'uppercase',
    backgroundColor: 'var(--accent)',
    color: 'white',
    padding: '0.2rem 0.5rem',
    borderRadius: '4px',
  },
  entryPattern: {
    fontSize: '0.9rem',
    color: 'var(--text-primary)',
    fontWeight: 500,
  },
  entryPatternSub: {
    fontSize: '0.8rem',
    color: 'var(--text-secondary)',
    fontFamily: 'ui-monospace, SFMono-Regular, SF Mono, Menlo, monospace',
  },
  entryActions: {
    display: 'flex',
    gap: '0.5rem',
  },
  toggleEnabled: {
    backgroundColor: 'rgba(52, 199, 89, 0.15)',
    border: '1px solid rgba(52, 199, 89, 0.3)',
    color: '#34c759',
  },
  toggleDisabled: {
    backgroundColor: 'rgba(142, 142, 147, 0.15)',
    border: '1px solid rgba(142, 142, 147, 0.3)',
    color: '#8e8e93',
  },
  removeButton: {
    backgroundColor: 'transparent',
    border: '1px solid rgba(255, 59, 48, 0.3)',
    borderRadius: '6px',
    padding: '0.4rem 0.75rem',
    fontSize: '0.8rem',
    color: '#ff3b30',
    cursor: 'pointer',
  },
  // Export styles
  exportSummary: {
    display: 'grid',
    gridTemplateColumns: 'repeat(2, 1fr)',
    gap: '0.75rem',
    marginBottom: '1rem',
  },
  summaryItem: {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
    backgroundColor: 'var(--bg-secondary)',
    border: '1px solid var(--border)',
    borderRadius: '8px',
    padding: '0.75rem 1rem',
  },
  summaryLabel: {
    fontSize: '0.85rem',
    color: 'var(--text-secondary)',
  },
  summaryValue: {
    fontSize: '1rem',
    fontWeight: 600,
    color: 'var(--text-primary)',
  },
  exportButton: {
    backgroundColor: 'var(--accent)',
    border: 'none',
    borderRadius: '8px',
    padding: '0.75rem 1.5rem',
    fontSize: '0.9rem',
    fontWeight: 500,
    color: 'white',
    cursor: 'pointer',
    width: '100%',
  },
  versionInfo: {
    marginTop: '1rem',
    fontSize: '0.85rem',
    color: 'var(--text-secondary)',
    textAlign: 'center' as const,
  },
  // Update section styles
  updateAvailable: {
    backgroundColor: 'rgba(52, 199, 89, 0.1)',
    border: '1px solid rgba(52, 199, 89, 0.3)',
    borderRadius: '8px',
    padding: '1rem',
    marginBottom: '1rem',
  },
  updateAvailableHeader: {
    display: 'flex',
    alignItems: 'center',
    gap: '0.5rem',
    fontSize: '0.95rem',
    fontWeight: 600,
    color: '#34c759',
    marginBottom: '0.5rem',
  },
  updateNotes: {
    fontSize: '0.85rem',
    color: 'var(--text-secondary)',
    marginBottom: '0.75rem',
    lineHeight: 1.5,
  },
  downloadButton: {
    backgroundColor: '#34c759',
    border: 'none',
    borderRadius: '6px',
    padding: '0.5rem 1rem',
    fontSize: '0.85rem',
    fontWeight: 500,
    color: 'white',
    cursor: 'pointer',
  },
  checkUpdateButton: {
    backgroundColor: 'var(--bg-secondary)',
    border: '1px solid var(--border)',
    borderRadius: '8px',
    padding: '0.75rem 1rem',
    fontSize: '0.9rem',
    fontWeight: 500,
    color: 'var(--text-primary)',
    cursor: 'pointer',
    width: '100%',
  },
  // API key status styles
  apiKeyStatus: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    backgroundColor: 'var(--bg-secondary)',
    border: '1px solid var(--border)',
    borderRadius: '8px',
    padding: '0.75rem 1rem',
    marginBottom: '0.75rem',
  },
  apiKeyStatusSet: {
    display: 'flex',
    alignItems: 'center',
    gap: '0.5rem',
    color: '#34c759',
    fontSize: '0.9rem',
    fontWeight: 500,
  },
  apiKeyStatusNotSet: {
    display: 'flex',
    alignItems: 'center',
    gap: '0.5rem',
    color: '#ff9500',
    fontSize: '0.9rem',
    fontWeight: 500,
  },
  clearButton: {
    backgroundColor: 'transparent',
    border: '1px solid rgba(255, 59, 48, 0.3)',
    borderRadius: '6px',
    padding: '0.4rem 0.75rem',
    fontSize: '0.8rem',
    color: '#ff3b30',
    cursor: 'pointer',
  },
  // Profile input styles
  profileInput: {
    width: '100%',
    backgroundColor: 'var(--bg-secondary)',
    border: '1px solid var(--border)',
    borderRadius: '8px',
    padding: '0.625rem 0.875rem',
    fontSize: '0.9rem',
    color: 'var(--text-primary)',
    outline: 'none',
  },
  profileTextarea: {
    width: '100%',
    backgroundColor: 'var(--bg-secondary)',
    border: '1px solid var(--border)',
    borderRadius: '8px',
    padding: '0.625rem 0.875rem',
    fontSize: '0.9rem',
    color: 'var(--text-primary)',
    outline: 'none',
    minHeight: '80px',
    resize: 'vertical' as const,
    fontFamily: 'inherit',
  },
  // Power saving and slider styles
  powerSavingOptions: {
    marginTop: '1rem',
    paddingTop: '1rem',
    borderTop: '1px solid var(--border)',
  },
  subLabel: {
    display: 'block',
    fontSize: '0.85rem',
    fontWeight: 500,
    color: 'var(--text-secondary)',
    marginBottom: '0.5rem',
  },
  infoBox: {
    display: 'flex',
    alignItems: 'flex-start',
    gap: '0.5rem',
    marginTop: '1rem',
    padding: '0.75rem 1rem',
    backgroundColor: 'rgba(0, 122, 255, 0.1)',
    border: '1px solid rgba(0, 122, 255, 0.2)',
    borderRadius: '8px',
    fontSize: '0.85rem',
    color: 'var(--text-secondary)',
    lineHeight: 1.5,
  },
  infoIcon: {
    fontSize: '1rem',
    flexShrink: 0,
  },
  sliderContainer: {
    display: 'flex',
    flexDirection: 'column' as const,
    gap: '0.5rem',
  },
  sliderLabels: {
    display: 'flex',
    justifyContent: 'space-between',
    fontSize: '0.75rem',
    color: 'var(--text-secondary)',
  },
  sliderLabelLeft: {
    textAlign: 'left' as const,
  },
  sliderLabelRight: {
    textAlign: 'right' as const,
  },
  sliderHint: {
    fontSize: '0.8rem',
    color: 'var(--text-secondary)',
    marginTop: '0.25rem',
  },
};

// Add global CSS for switch styling (checkboxes)
const styleTag = document.createElement('style');
styleTag.textContent = `
  .settings-switch input {
    opacity: 0;
    width: 0;
    height: 0;
  }
  .settings-switch span {
    background-color: #48484a;
    border-color: #48484a;
  }
  .settings-switch input:checked + span {
    background-color: #34c759;
    border-color: #34c759;
  }
  .settings-switch span:before {
    position: absolute;
    content: "";
    height: 18px;
    width: 18px;
    left: 2px;
    bottom: 2px;
    background-color: white;
    transition: .2s;
    border-radius: 50%;
  }
  .settings-switch input:checked + span:before {
    transform: translateX(20px);
  }
`;
if (!document.head.querySelector('style[data-settings]')) {
  styleTag.setAttribute('data-settings', 'true');
  document.head.appendChild(styleTag);
}

export default Settings;
