import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import type { AllSettings, AppSettings, BlocklistEntry, InstalledApp } from '../types/trace-api';

// Screenshot quality level helpers
type QualityLevel = 'standard' | 'high' | 'ultra';

function getQualityLevel(value: number): QualityLevel {
  if (value <= 70) return 'standard';
  if (value <= 90) return 'high';
  return 'ultra';
}

function getQualityValue(level: string): number {
  switch (level) {
    case 'standard': return 70;
    case 'high': return 85;
    case 'ultra': return 95;
    default: return 85;
  }
}

// Deduplication sensitivity level helpers
type DedupLevel = 'very_strict' | 'strict' | 'balanced' | 'relaxed';

function getDedupLevel(value: number): DedupLevel {
  if (value <= 2) return 'very_strict';
  if (value <= 4) return 'strict';
  if (value <= 7) return 'balanced';
  return 'relaxed';
}

function getDedupValue(level: string): number {
  switch (level) {
    case 'very_strict': return 2;
    case 'strict': return 4;
    case 'balanced': return 6;
    case 'relaxed': return 10;
    default: return 6;
  }
}

// Tab definitions
type SettingsTab = 'general' | 'capture' | 'ai' | 'privacy' | 'advanced';

const TABS: { id: SettingsTab; label: string; icon: string }[] = [
  { id: 'general', label: 'General', icon: '⚙️' },
  { id: 'capture', label: 'Capture', icon: '📷' },
  { id: 'ai', label: 'AI & APIs', icon: '🤖' },
  { id: 'privacy', label: 'Privacy', icon: '🔒' },
  { id: 'advanced', label: 'Advanced', icon: '🔧' },
];

export function Settings() {
  const navigate = useNavigate();
  const [activeTab, setActiveTab] = useState<SettingsTab>('general');
  const [settings, setSettings] = useState<AllSettings | null>(null);
  const [apiKey, setApiKey] = useState('');
  const [tavilyApiKey, setTavilyApiKey] = useState('');
  const [hasTavilyKey, setHasTavilyKey] = useState(false);
  const [tavilyUsage, setTavilyUsage] = useState<{
    count: number;
    remaining: number;
    limit: number;
    percentage: number;
    warning: boolean;
    auto_disabled: boolean;
  } | null>(null);
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

  // User profile state (legacy - keeping for migration)
  const [, setUserProfile] = useState({
    name: '',
    age: '',
    interests: '',
    languages: '',
    additional_info: '',
  });

  // Memory state
  const [memorySummary, setMemorySummary] = useState<string>('');
  const [memoryLoading, setMemoryLoading] = useState(false);
  const [showRestartConfirm, setShowRestartConfirm] = useState(false);

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

  // Shortcuts state
  const [shortcutsEnabled, setShortcutsEnabled] = useState(true);

  // Reset data state
  const [showResetConfirm, setShowResetConfirm] = useState(false);
  const [resetLoading, setResetLoading] = useState(false);
  const [dataSummary, setDataSummary] = useState<{
    notes_count: number;
    notes_size_bytes: number;
    database_exists: boolean;
    tables_with_data: { table: string; count: number }[];
    memory_exists: boolean;
    cache_size_bytes: number;
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

  const loadMemorySummary = async () => {
    setMemoryLoading(true);
    try {
      const result = await window.traceAPI.onboarding.getSummary();
      if (result.success && result.summary) {
        setMemorySummary(result.summary);
      }
    } catch (err) {
      console.error('Failed to load memory summary:', err);
    } finally {
      setMemoryLoading(false);
    }
  };

  const loadTavilyKeyStatus = async () => {
    try {
      const result = await window.traceAPI.settings.getTavilyApiKey();
      setHasTavilyKey(result.has_api_key);

      // Also load usage stats
      const usage = await window.traceAPI.settings.getTavilyUsage();
      setTavilyUsage(usage);
    } catch (err) {
      console.error('Failed to load Tavily key status:', err);
    }
  };

  const loadDataSummary = async () => {
    try {
      const result = await window.traceAPI.settings.getDataSummary();
      setDataSummary(result);
    } catch (err) {
      console.error('Failed to load data summary:', err);
    }
  };

  const handleResetAllData = async () => {
    setResetLoading(true);
    try {
      const result = await window.traceAPI.settings.resetAllData();
      if (result.success) {
        setMessage({ type: 'success', text: 'All data has been reset successfully.' });
        setShowResetConfirm(false);
        // Reload summaries
        loadDataSummary();
        loadMemorySummary();
        // Also reload export summary
        try {
          const exportResult = await window.traceAPI.export.summary();
          if (exportResult.success) {
            setExportSummary({
              notes_in_db: exportResult.notes_in_db,
              markdown_files: exportResult.markdown_files,
              entities: exportResult.entities,
              edges: exportResult.edges,
            });
          }
        } catch {}
      } else {
        setMessage({ type: 'error', text: `Reset completed with errors: ${result.errors.join(', ')}` });
      }
    } catch (err) {
      console.error('Failed to reset data:', err);
      setMessage({ type: 'error', text: 'Failed to reset data. Please try again.' });
    } finally {
      setResetLoading(false);
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
    loadMemorySummary();
    loadDataSummary();
    loadTavilyKeyStatus();

    // Load app version
    window.traceAPI.getVersion().then(setAppVersion).catch(() => {});

    // Load shortcuts enabled state
    window.traceAPI.shortcuts.isEnabled()
      .then((result) => setShortcutsEnabled(result.enabled ?? true))
      .catch(() => {});

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

  const handleSaveTavilyKey = async () => {
    if (!tavilyApiKey.trim()) return;

    setSaving(true);
    setMessage(null);
    try {
      await window.traceAPI.settings.setTavilyApiKey(tavilyApiKey.trim());
      setMessage({ type: 'success', text: 'Tavily API key saved successfully. Web search is now enabled.' });
      setTavilyApiKey('');
      setHasTavilyKey(true);
      // Load usage stats
      const usage = await window.traceAPI.settings.getTavilyUsage();
      setTavilyUsage(usage);
    } catch (err) {
      setMessage({ type: 'error', text: err instanceof Error ? err.message : 'Failed to save Tavily API key' });
    } finally {
      setSaving(false);
    }
  };

  const handleClearTavilyKey = async () => {
    setMessage(null);
    try {
      await window.traceAPI.settings.setValue('tavily_api_key', null);
      setMessage({ type: 'success', text: 'Tavily API key cleared. Web search is now disabled.' });
      setHasTavilyKey(false);
    } catch (err) {
      setMessage({ type: 'error', text: err instanceof Error ? err.message : 'Failed to clear Tavily API key' });
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

  const formatBytes = (bytes: number) => {
    if (bytes === 0) return '0 B';
    const k = 1024;
    const sizes = ['B', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return `${parseFloat((bytes / Math.pow(k, i)).toFixed(1))} ${sizes[i]}`;
  };

  if (loading) {
    return (
      <div style={styles.container}>
        <div className="titlebar" style={styles.titlebar} />
        <div style={styles.loadingContainer}>
          <div style={styles.loading}>Loading settings...</div>
        </div>
      </div>
    );
  }

  // Render tab content based on active tab
  const renderTabContent = () => {
    switch (activeTab) {
      case 'general':
        return (
          <>
            {/* Appearance */}
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

            {/* Notifications */}
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

            {/* Keyboard Shortcuts */}
            <section style={styles.section}>
              <h2 style={styles.sectionTitle}>Keyboard Shortcuts</h2>
              <div style={styles.field}>
                <div style={styles.toggleRow}>
                  <div>
                    <label style={styles.label}>Enable Global Shortcuts</label>
                    <p style={styles.description}>Allow Trace to respond to keyboard shortcuts even when not focused.</p>
                  </div>
                  <label className="settings-switch" style={styles.switch}>
                    <input
                      type="checkbox"
                      checked={shortcutsEnabled}
                      onChange={async (e) => {
                        const enabled = e.target.checked;
                        setShortcutsEnabled(enabled);
                        await window.traceAPI.shortcuts.setEnabled(enabled);
                        await handleSettingChange('shortcuts.enabled', enabled);
                      }}
                    />
                    <span style={styles.switchSlider}></span>
                  </label>
                </div>
              </div>
              <div style={{ ...styles.field, opacity: shortcutsEnabled ? 1 : 0.5 }}>
                <label style={styles.label}>Open Trace</label>
                <p style={styles.description}>Global shortcut to show/hide the Trace window.</p>
                <div style={styles.shortcutDisplay}>
                  {settings?.config.shortcuts.open_trace?.replace('CommandOrControl', '⌘').replace('+', ' + ') ?? '⌘ + Shift + T'}
                </div>
              </div>
              <div style={{ ...styles.field, opacity: shortcutsEnabled ? 1 : 0.5 }}>
                <label style={styles.label}>Quick Capture</label>
                <p style={styles.description}>Global shortcut to open Trace and focus the chat input.</p>
                <div style={styles.shortcutDisplay}>⌘ + Shift + N</div>
              </div>
              <div style={styles.field}>
                <label style={styles.label}>Open Settings</label>
                <p style={styles.description}>Open settings from anywhere in the app.</p>
                <div style={styles.shortcutDisplay}>⌘ + ,</div>
              </div>
            </section>
          </>
        );

      case 'capture':
        return (
          <>
            {/* Power Saving */}
            <section style={styles.section}>
              <h2 style={styles.sectionTitle}>Power Saving</h2>
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
              </div>
            </section>

            {/* Capture Settings */}
            <section style={styles.section}>
              <h2 style={styles.sectionTitle}>Capture Settings</h2>
              <div style={styles.field}>
                <label style={styles.label}>Screenshot Quality</label>
                <p style={styles.description}>
                  Choose the clarity of captured screenshots. Higher quality produces clearer text but uses more storage.
                </p>
                <select
                  value={getQualityLevel(settings?.config.capture.jpeg_quality ?? 85)}
                  onChange={(e) => handleSettingChange('capture.jpeg_quality', getQualityValue(e.target.value))}
                  style={styles.select}
                >
                  <option value="standard">Standard – Smaller files, good for general use</option>
                  <option value="high">High – Clear text, recommended for most users</option>
                  <option value="ultra">Ultra – Maximum clarity, larger files</option>
                </select>
              </div>

              <div style={styles.field}>
                <label style={styles.label}>Change Detection</label>
                <p style={styles.description}>
                  How sensitive Trace is to screen changes. Stricter settings capture more subtle changes but use more storage.
                </p>
                <select
                  value={getDedupLevel(settings?.config.capture.dedup_threshold ?? 5)}
                  onChange={(e) => handleSettingChange('capture.dedup_threshold', getDedupValue(e.target.value))}
                  style={styles.select}
                >
                  <option value="very_strict">Very Strict – Best for coding, terminals, and detailed work</option>
                  <option value="strict">Strict – Catches small text and UI changes</option>
                  <option value="balanced">Balanced – Good for most activities (recommended)</option>
                  <option value="relaxed">Relaxed – Saves storage, best for video/browsing</option>
                </select>
                <p style={{...styles.description, marginTop: '8px', fontSize: '12px', color: '#888'}}>
                  {getDedupLevel(settings?.config.capture.dedup_threshold ?? 5) === 'very_strict'
                    ? '💡 Ideal for developers, writers, and professionals where small text changes matter.'
                    : getDedupLevel(settings?.config.capture.dedup_threshold ?? 5) === 'strict'
                    ? '💡 Good for work that involves frequent small updates to documents or code.'
                    : getDedupLevel(settings?.config.capture.dedup_threshold ?? 5) === 'balanced'
                    ? '💡 Works well for mixed activities like browsing, reading, and light work.'
                    : '💡 Best when watching videos, browsing social media, or other visual content.'}
                </p>
              </div>
            </section>

            {/* Processing */}
            <section style={styles.section}>
              <h2 style={styles.sectionTitle}>Processing</h2>
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
            </section>
          </>
        );

      case 'ai':
        return (
          <>
            {/* API Configuration */}
            <section style={styles.section}>
              <h2 style={styles.sectionTitle}>API Configuration</h2>
              <div style={styles.field}>
                <label style={styles.label}>OpenAI API Key</label>
                <p style={styles.description}>
                  Required for generating summaries and answering queries.
                </p>

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

              <div style={styles.field}>
                <label style={styles.label}>Tavily API Key (Web Search)</label>
                <p style={styles.description}>
                  Optional. Enables web search to augment chat answers with current information.{' '}
                  <a
                    href="#"
                    onClick={(e) => {
                      e.preventDefault();
                      window.traceAPI?.shell?.openExternal('https://tavily.com');
                    }}
                    style={{ color: 'var(--accent)' }}
                  >
                    Get a free key
                  </a>
                  {' '}(1,000 free searches/month)
                </p>

                {/* Status indicator - consistent with OpenAI section */}
                <div style={styles.apiKeyStatus}>
                  {hasTavilyKey ? (
                    <>
                      <span style={styles.apiKeyStatusSet}>
                        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                          <path d="M20 6L9 17l-5-5" />
                        </svg>
                        Web search enabled
                      </span>
                      <button
                        onClick={handleClearTavilyKey}
                        style={styles.clearButton}
                        type="button"
                      >
                        Clear
                      </button>
                    </>
                  ) : (
                    <span style={styles.apiKeyStatusOptional}>
                      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                        <circle cx="12" cy="12" r="10" />
                        <line x1="12" y1="8" x2="12" y2="12" />
                        <line x1="12" y1="16" x2="12.01" y2="16" />
                      </svg>
                      Not configured (optional)
                    </span>
                  )}
                </div>

                {/* Usage stats when key is set */}
                {hasTavilyKey && tavilyUsage && (
                  <div style={styles.usageStatsBox}>
                    <div style={styles.usageBar}>
                      <div
                        style={{
                          ...styles.usageBarFill,
                          width: `${Math.min(tavilyUsage.percentage, 100)}%`,
                          backgroundColor: tavilyUsage.warning
                            ? tavilyUsage.auto_disabled
                              ? '#ff3b30'
                              : '#ff9500'
                            : 'var(--accent)',
                        }}
                      />
                    </div>
                    <div style={styles.usageText}>
                      <span>{tavilyUsage.count} / {tavilyUsage.limit} searches this month</span>
                      <span style={{ color: 'var(--text-secondary)' }}>{tavilyUsage.remaining} remaining</span>
                    </div>
                    {tavilyUsage.warning && (
                      <p style={{
                        ...styles.usageWarning,
                        color: tavilyUsage.auto_disabled ? '#ff3b30' : '#ff9500',
                      }}>
                        {tavilyUsage.auto_disabled
                          ? '⚠️ Auto web search disabled (95% limit). Explicit requests still work.'
                          : '⚠️ Approaching monthly limit (80%)'}
                      </p>
                    )}
                  </div>
                )}

                {/* Input for new key - only show when not set */}
                {!hasTavilyKey && (
                  <div style={styles.inputRow}>
                    <input
                      type="password"
                      value={tavilyApiKey}
                      onChange={(e) => setTavilyApiKey(e.target.value)}
                      placeholder="Enter API key (tvly-...)"
                      style={styles.input}
                    />
                    <button
                      onClick={handleSaveTavilyKey}
                      disabled={!tavilyApiKey.trim() || saving}
                      style={{
                        ...styles.saveButton,
                        ...(!tavilyApiKey.trim() || saving ? styles.saveButtonDisabled : {}),
                      }}
                    >
                      {saving ? 'Saving...' : 'Save'}
                    </button>
                  </div>
                )}
              </div>
            </section>

            {/* AI Models */}
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
          </>
        );

      case 'privacy':
        return (
          <>
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
              <div style={styles.blocklistTabContainer}>
                <button
                  style={{
                    ...styles.blocklistTab,
                    ...(newBlockType === 'app' ? styles.blocklistTabActive : {}),
                  }}
                  onClick={() => setNewBlockType('app')}
                >
                  Block Apps
                </button>
                <button
                  style={{
                    ...styles.blocklistTab,
                    ...(newBlockType === 'domain' ? styles.blocklistTabActive : {}),
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
          </>
        );

      case 'advanced':
        return (
          <>
            {/* Memory & Personalization */}
            <section style={styles.section}>
              <h2 style={styles.sectionTitle}>Memory & Personalization</h2>
              <p style={styles.description}>
                Trace learns about you through conversations to personalize your experience.
              </p>

              {memorySummary && (
                <div style={styles.memorySummaryBox}>
                  <div style={styles.memorySummaryTitle}>What Trace knows about you:</div>
                  <div style={styles.memorySummaryContent}>
                    {memoryLoading ? 'Loading...' : memorySummary}
                  </div>
                </div>
              )}

              <div style={styles.memoryButtonsContainer}>
                <button
                  onClick={() => navigate('/onboarding/profile', { state: { mode: 'update' } })}
                  style={styles.memoryButton}
                >
                  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                    <path d="M12 20h9" />
                    <path d="M16.5 3.5a2.121 2.121 0 0 1 3 3L7 19l-4 1 1-4L16.5 3.5z" />
                  </svg>
                  Update Memory
                </button>
                <button
                  onClick={() => setShowRestartConfirm(true)}
                  style={styles.memoryButtonSecondary}
                >
                  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                    <path d="M23 4v6h-6" />
                    <path d="M1 20v-6h6" />
                    <path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15" />
                  </svg>
                  Restart Onboarding
                </button>
              </div>

              {showRestartConfirm && (
                <div style={styles.confirmDialog}>
                  <div style={styles.confirmDialogContent}>
                    <p style={styles.confirmText}>
                      This will clear all your memory data and start the onboarding process from scratch. Are you sure?
                    </p>
                    <div style={styles.confirmButtons}>
                      <button
                        onClick={() => setShowRestartConfirm(false)}
                        style={styles.confirmCancelButton}
                      >
                        Cancel
                      </button>
                      <button
                        onClick={() => {
                          setShowRestartConfirm(false);
                          navigate('/onboarding/profile', { state: { mode: 'restart' } });
                        }}
                        style={styles.confirmDangerButton}
                      >
                        Yes, Restart
                      </button>
                    </div>
                  </div>
                </div>
              )}
            </section>

            {/* Data Management */}
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

            {/* Export & Backup */}
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

            {/* Reset All Data */}
            <section style={styles.section}>
              <h2 style={styles.sectionTitle}>Reset All Data</h2>
              <p style={styles.description}>
                Permanently delete all your Trace data including notes, entities, relationships, and user memory.
                <strong style={{ color: '#ef4444' }}> This action cannot be undone.</strong>
              </p>

              {dataSummary && (dataSummary.notes_count > 0 || dataSummary.memory_exists) && (
                <div style={styles.resetWarning}>
                  <div style={styles.warningHeader}>
                    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#ef4444" strokeWidth="2">
                      <path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z" />
                      <line x1="12" y1="9" x2="12" y2="13" />
                      <line x1="12" y1="17" x2="12.01" y2="17" />
                    </svg>
                    <span>Data that will be deleted:</span>
                  </div>
                  <ul style={styles.resetDataList}>
                    {dataSummary.notes_count > 0 && (
                      <li>{dataSummary.notes_count} notes ({formatBytes(dataSummary.notes_size_bytes)})</li>
                    )}
                    {dataSummary.tables_with_data.map((t) => (
                      <li key={t.table}>{t.count} {t.table.replace('_', ' ')}</li>
                    ))}
                    {dataSummary.memory_exists && <li>User memory profile</li>}
                    {dataSummary.cache_size_bytes > 0 && (
                      <li>Cache ({formatBytes(dataSummary.cache_size_bytes)})</li>
                    )}
                  </ul>
                  <p style={styles.backupReminder}>
                    We recommend exporting your data first using the Export feature above.
                  </p>
                </div>
              )}

              {!showResetConfirm ? (
                <button
                  onClick={() => setShowResetConfirm(true)}
                  style={styles.resetButton}
                >
                  Reset All Data
                </button>
              ) : (
                <div style={styles.resetConfirmBox}>
                  <p style={styles.resetConfirmText}>
                    Are you sure you want to delete all your data? This cannot be undone.
                  </p>
                  <div style={styles.resetConfirmButtons}>
                    <button
                      onClick={() => setShowResetConfirm(false)}
                      style={styles.cancelButton}
                      disabled={resetLoading}
                    >
                      Cancel
                    </button>
                    <button
                      onClick={handleResetAllData}
                      disabled={resetLoading}
                      style={{
                        ...styles.confirmResetButton,
                        ...(resetLoading ? styles.saveButtonDisabled : {}),
                      }}
                    >
                      {resetLoading ? 'Resetting...' : 'Yes, Delete Everything'}
                    </button>
                  </div>
                </div>
              )}
            </section>

            {/* Updates */}
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

            {/* About */}
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
          </>
        );
    }
  };

  return (
    <div style={styles.container}>
      <div className="titlebar" style={styles.titlebar} />
      <div style={styles.layout}>
        {/* Sidebar with tabs */}
        <nav style={styles.sidebar}>
          <div style={styles.sidebarHeader}>
            <button onClick={() => navigate(-1)} style={styles.backButton}>
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M19 12H5" />
                <path d="M12 19l-7-7 7-7" />
              </svg>
              Back
            </button>
          </div>
          <div style={styles.tabList}>
            {TABS.map((tab) => (
              <button
                key={tab.id}
                onClick={() => setActiveTab(tab.id)}
                style={{
                  ...styles.tabButton,
                  ...(activeTab === tab.id ? styles.tabButtonActive : {}),
                }}
              >
                <span style={styles.tabIcon}>{tab.icon}</span>
                <span>{tab.label}</span>
              </button>
            ))}
          </div>
        </nav>

        {/* Main content area - scrollable */}
        <main style={styles.main}>
          <div style={styles.contentWrapper}>
            <h1 style={styles.title}>
              {TABS.find(t => t.id === activeTab)?.label}
            </h1>

            {message && (
              <div style={{
                ...styles.message,
                ...(message.type === 'success' ? styles.messageSuccess : styles.messageError),
              }}>
                {message.text}
              </div>
            )}

            {renderTabContent()}
          </div>
        </main>
      </div>
    </div>
  );
}

const styles: Record<string, React.CSSProperties> = {
  container: {
    flex: 1,
    display: 'flex',
    flexDirection: 'column',
    height: '100%',
    overflow: 'hidden',
  },
  titlebar: {
    minHeight: '36px',
    flexShrink: 0,
  },
  layout: {
    flex: 1,
    display: 'flex',
    minHeight: 0,
    overflow: 'hidden',
  },
  sidebar: {
    width: '200px',
    flexShrink: 0,
    backgroundColor: 'var(--bg-secondary)',
    borderRight: '1px solid var(--border)',
    display: 'flex',
    flexDirection: 'column',
    padding: '1rem 0',
  },
  sidebarHeader: {
    padding: '0 1rem 1rem',
    borderBottom: '1px solid var(--border)',
    marginBottom: '0.5rem',
  },
  backButton: {
    display: 'flex',
    alignItems: 'center',
    gap: '0.5rem',
    backgroundColor: 'transparent',
    border: 'none',
    color: 'var(--accent)',
    fontSize: '0.85rem',
    cursor: 'pointer',
    padding: '0.5rem',
    borderRadius: '6px',
    width: '100%',
  },
  tabList: {
    display: 'flex',
    flexDirection: 'column',
    gap: '2px',
    padding: '0 0.5rem',
  },
  tabButton: {
    display: 'flex',
    alignItems: 'center',
    gap: '0.75rem',
    padding: '0.625rem 0.75rem',
    backgroundColor: 'transparent',
    border: 'none',
    borderRadius: '6px',
    fontSize: '0.9rem',
    color: 'var(--text-secondary)',
    cursor: 'pointer',
    textAlign: 'left',
    transition: 'all 0.15s ease',
  },
  tabButtonActive: {
    backgroundColor: 'var(--accent)',
    color: 'white',
  },
  tabIcon: {
    fontSize: '1rem',
    width: '20px',
    textAlign: 'center',
  },
  main: {
    flex: 1,
    overflowY: 'auto',
    overflowX: 'hidden',
  },
  contentWrapper: {
    maxWidth: '600px',
    padding: '2rem',
    margin: '0 auto',
  },
  loadingContainer: {
    flex: 1,
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
  },
  title: {
    fontSize: '1.5rem',
    fontWeight: 600,
    color: 'var(--text-primary)',
    marginBottom: '1.5rem',
  },
  loading: {
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
  tavilyNote: {
    fontSize: '0.8rem',
    color: 'var(--text-secondary)',
    fontStyle: 'italic',
    backgroundColor: 'rgba(0, 122, 255, 0.08)',
    padding: '0.75rem',
    borderRadius: '8px',
    marginTop: '0.5rem',
    lineHeight: 1.5,
  },
  tavilyConfigured: {
    display: 'flex',
    flexDirection: 'column' as const,
    gap: '0.75rem',
  },
  keyConfigured: {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
  },
  keyStatus: {
    color: '#34c759',
    fontWeight: 500,
    fontSize: '0.9rem',
  },
  usageStats: {
    display: 'flex',
    flexDirection: 'column' as const,
    gap: '0.5rem',
  },
  usageBar: {
    height: '8px',
    backgroundColor: 'var(--border)',
    borderRadius: '4px',
    overflow: 'hidden',
  },
  usageBarFill: {
    height: '100%',
    borderRadius: '4px',
    transition: 'width 0.3s ease, background-color 0.3s ease',
  },
  usageText: {
    display: 'flex',
    justifyContent: 'space-between',
    fontSize: '0.8rem',
    color: 'var(--text-primary)',
  },
  usageStatsBox: {
    backgroundColor: 'var(--bg-tertiary)',
    borderRadius: '8px',
    padding: '0.75rem 1rem',
    marginBottom: '0.75rem',
    display: 'flex',
    flexDirection: 'column' as const,
    gap: '0.5rem',
  },
  usageWarning: {
    fontSize: '0.8rem',
    margin: 0,
    fontWeight: 500,
  },
  inputRow: {
    display: 'flex',
    gap: '0.5rem',
  },
  inputGroup: {
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
  button: {
    backgroundColor: 'var(--accent)',
    border: 'none',
    borderRadius: '8px',
    padding: '0.625rem 1.25rem',
    fontSize: '0.9rem',
    fontWeight: 500,
    color: 'white',
    cursor: 'pointer',
  },
  buttonDisabled: {
    backgroundColor: '#404040',
    cursor: 'not-allowed',
    opacity: 0.5,
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
    borderRadius: '24px',
  },
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
    width: '100%',
    WebkitAppearance: 'menulist',
  },
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
  blocklistTabContainer: {
    display: 'flex',
    gap: '0.5rem',
    marginBottom: '1rem',
  },
  blocklistTab: {
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
  blocklistTabActive: {
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
  apiKeyStatusOptional: {
    display: 'flex',
    alignItems: 'center',
    gap: '0.5rem',
    color: 'var(--text-secondary)',
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
  memorySummaryBox: {
    backgroundColor: 'var(--bg-secondary)',
    border: '1px solid var(--border)',
    borderRadius: '8px',
    padding: '1rem',
    marginBottom: '1rem',
  },
  memorySummaryTitle: {
    fontSize: '0.85rem',
    fontWeight: 600,
    color: 'var(--text-primary)',
    marginBottom: '0.5rem',
  },
  memorySummaryContent: {
    fontSize: '0.85rem',
    color: 'var(--text-secondary)',
    lineHeight: 1.6,
  },
  memoryButtonsContainer: {
    display: 'flex',
    gap: '0.75rem',
  },
  memoryButton: {
    flex: 1,
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    gap: '0.5rem',
    padding: '0.875rem 1rem',
    backgroundColor: 'var(--accent)',
    border: 'none',
    borderRadius: '8px',
    fontSize: '0.9rem',
    fontWeight: 500,
    color: 'white',
    cursor: 'pointer',
    transition: 'all 0.2s ease',
  },
  memoryButtonSecondary: {
    flex: 1,
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    gap: '0.5rem',
    padding: '0.875rem 1rem',
    backgroundColor: 'var(--bg-secondary)',
    border: '1px solid var(--border)',
    borderRadius: '8px',
    fontSize: '0.9rem',
    fontWeight: 500,
    color: 'var(--text-primary)',
    cursor: 'pointer',
    transition: 'all 0.2s ease',
  },
  confirmDialog: {
    marginTop: '1rem',
    backgroundColor: 'rgba(255, 59, 48, 0.1)',
    border: '1px solid rgba(255, 59, 48, 0.3)',
    borderRadius: '8px',
    padding: '1rem',
  },
  confirmDialogContent: {
    display: 'flex',
    flexDirection: 'column' as const,
    gap: '1rem',
  },
  confirmText: {
    fontSize: '0.9rem',
    color: 'var(--text-primary)',
    margin: 0,
    lineHeight: 1.5,
  },
  confirmButtons: {
    display: 'flex',
    gap: '0.5rem',
    justifyContent: 'flex-end',
  },
  confirmCancelButton: {
    padding: '0.5rem 1rem',
    backgroundColor: 'var(--bg-secondary)',
    border: '1px solid var(--border)',
    borderRadius: '6px',
    fontSize: '0.85rem',
    color: 'var(--text-primary)',
    cursor: 'pointer',
  },
  confirmDangerButton: {
    padding: '0.5rem 1rem',
    backgroundColor: '#ff3b30',
    border: 'none',
    borderRadius: '6px',
    fontSize: '0.85rem',
    fontWeight: 500,
    color: 'white',
    cursor: 'pointer',
  },
  resetWarning: {
    backgroundColor: 'rgba(255, 59, 48, 0.1)',
    border: '1px solid rgba(255, 59, 48, 0.3)',
    borderRadius: '8px',
    padding: '1rem',
    marginBottom: '1rem',
  },
  warningHeader: {
    display: 'flex',
    alignItems: 'center',
    gap: '0.5rem',
    fontSize: '0.9rem',
    fontWeight: 600,
    color: '#ef4444',
    marginBottom: '0.75rem',
  },
  resetDataList: {
    margin: '0 0 0.75rem 1.25rem',
    padding: 0,
    fontSize: '0.85rem',
    color: 'var(--text-primary)',
    lineHeight: 1.6,
  },
  backupReminder: {
    fontSize: '0.85rem',
    color: 'var(--text-secondary)',
    fontStyle: 'italic',
    margin: 0,
  },
  resetButton: {
    backgroundColor: 'transparent',
    border: '1px solid rgba(255, 59, 48, 0.5)',
    borderRadius: '8px',
    padding: '0.75rem 1.5rem',
    fontSize: '0.9rem',
    fontWeight: 500,
    color: '#ef4444',
    cursor: 'pointer',
    width: '100%',
  },
  resetConfirmBox: {
    backgroundColor: 'rgba(255, 59, 48, 0.1)',
    border: '1px solid rgba(255, 59, 48, 0.3)',
    borderRadius: '8px',
    padding: '1rem',
  },
  resetConfirmText: {
    fontSize: '0.9rem',
    color: 'var(--text-primary)',
    margin: '0 0 1rem 0',
    lineHeight: 1.5,
  },
  resetConfirmButtons: {
    display: 'flex',
    gap: '0.5rem',
    justifyContent: 'flex-end',
  },
  cancelButton: {
    padding: '0.5rem 1rem',
    backgroundColor: 'var(--bg-secondary)',
    border: '1px solid var(--border)',
    borderRadius: '6px',
    fontSize: '0.85rem',
    color: 'var(--text-primary)',
    cursor: 'pointer',
  },
  confirmResetButton: {
    padding: '0.5rem 1rem',
    backgroundColor: '#ef4444',
    border: 'none',
    borderRadius: '6px',
    fontSize: '0.85rem',
    fontWeight: 500,
    color: 'white',
    cursor: 'pointer',
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
    background: linear-gradient(to right, #8e8e93, #a8a8ad);
    border: none;
    transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
  }
  .settings-switch input:checked + span {
    background: linear-gradient(to right, #4a90d9, #5a9fe0);
  }
  .settings-switch span:before {
    position: absolute;
    content: "";
    height: 20px;
    width: 20px;
    left: 2px;
    bottom: 2px;
    background: linear-gradient(to bottom, #ffffff, #f0f0f0);
    transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
    border-radius: 50%;
    box-shadow: 0 1px 3px rgba(0, 0, 0, 0.3), inset 0 1px 0 rgba(255, 255, 255, 0.8);
    border: 0.5px solid rgba(0, 0, 0, 0.15);
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
