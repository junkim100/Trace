/**
 * Auto-Updater Module for Trace
 *
 * Main orchestrator for the auto-update system. Coordinates between
 * the release checker, dialog UI, and settings manager.
 *
 * Current implementation: Manual download via browser
 * Future: Can be upgraded to electron-updater when code signing is added
 */

const GitHubReleaseChecker = require('./github-release-checker');
const {
  showUpdateDialog,
  showNoUpdateDialog,
  showUpdateErrorDialog,
  openReleasePage,
  showUpdateNotification,
} = require('./update-dialog');
const UpdateSettings = require('./update-settings');

class AutoUpdater {
  /**
   * Create auto-updater instance
   * @param {Object} options - Configuration options
   * @param {Function} options.pythonCall - Function to call Python backend
   */
  constructor(options = {}) {
    this.mainWindow = null;
    this.pythonCall = options.pythonCall;
    this.checker = new GitHubReleaseChecker();
    this.settings = new UpdateSettings(this.pythonCall);
    this._checkInterval = null;
    this._initialized = false;
  }

  /**
   * Set the main window reference
   * @param {BrowserWindow} window - Main application window
   */
  setMainWindow(window) {
    this.mainWindow = window;
  }

  /**
   * Initialize the auto-updater
   * Called after Python backend is ready
   */
  async initialize() {
    if (this._initialized) return;

    try {
      const settings = await this.settings.getSettings();

      // Check on launch if enabled (with delay to avoid blocking startup)
      // Silent mode: only notify if update is available, no popup when up-to-date
      if (settings.check_on_launch !== false) {
        setTimeout(() => {
          this.checkForUpdates({ silent: true });
        }, 5000); // 5 second delay
      }

      // Start periodic checks if enabled
      if (settings.check_periodically !== false) {
        const interval = settings.check_interval_hours || 24;
        this.startPeriodicChecks(interval);
      }

      this._initialized = true;
      console.log('Auto-updater initialized');
    } catch (error) {
      console.error('Failed to initialize auto-updater:', error);
    }
  }

  /**
   * Check for available updates
   * @param {Object} options - Check options
   * @param {boolean} options.silent - Don't show "no update" dialog
   * @param {boolean} options.force - Bypass cache and skip checks
   * @returns {Promise<Object>} Check result
   */
  async checkForUpdates(options = {}) {
    const { silent = false, force = false } = options;

    try {
      // Check if we should skip (remind later is active)
      if (!force) {
        const shouldRemind = await this.settings.shouldRemindLater();
        if (shouldRemind) {
          return { checked: false, reason: 'remind_later_active' };
        }
      }

      // Perform the update check
      const updateInfo = await this.checker.checkForUpdate(force);

      // Update last check timestamp
      await this.settings.updateLastCheckTimestamp();

      // Handle errors
      if (updateInfo.error) {
        if (!silent && this.mainWindow) {
          await showUpdateErrorDialog(this.mainWindow, updateInfo.error);
        }
        return { checked: true, error: updateInfo.error };
      }

      // No update available
      if (!updateInfo.available) {
        if (!silent && this.mainWindow) {
          await showNoUpdateDialog(this.mainWindow, updateInfo.currentVersion);
        }
        return { checked: true, available: false, currentVersion: updateInfo.currentVersion };
      }

      // Check if this version is skipped
      const isSkipped = await this.settings.isVersionSkipped(updateInfo.latestVersion);
      if (isSkipped && !force) {
        return { checked: true, available: true, skipped: true, updateInfo };
      }

      // Show update dialog or notification
      if (silent) {
        // Background check - show notification
        showUpdateNotification(updateInfo);
      } else if (this.mainWindow) {
        // Foreground check - show dialog
        const result = await showUpdateDialog(this.mainWindow, updateInfo);
        await this._handleDialogResult(result, updateInfo);
      }

      return { checked: true, available: true, updateInfo };
    } catch (error) {
      console.error('Update check failed:', error);
      if (!silent && this.mainWindow) {
        await showUpdateErrorDialog(this.mainWindow, error.message);
      }
      return { checked: true, error: error.message };
    }
  }

  /**
   * Handle user's dialog choice
   * @param {Object} result - Dialog result
   * @param {Object} updateInfo - Update information
   */
  async _handleDialogResult(result, updateInfo) {
    switch (result.action) {
      case 'download':
        // Open release page in browser
        openReleasePage(updateInfo.releaseUrl);
        break;

      case 'later':
        // Set remind later for 24 hours
        await this.settings.setRemindLater(24);
        break;

      case 'skip':
        // Add version to skip list
        await this.settings.skipVersion(result.version);
        break;
    }
  }

  /**
   * Start periodic update checks
   * @param {number} intervalHours - Hours between checks
   */
  startPeriodicChecks(intervalHours = 24) {
    // Clear any existing interval
    this.stopPeriodicChecks();

    const intervalMs = intervalHours * 60 * 60 * 1000;

    this._checkInterval = setInterval(() => {
      this.checkForUpdates({ silent: true });
    }, intervalMs);

    console.log(`Periodic update checks started (every ${intervalHours} hours)`);
  }

  /**
   * Stop periodic update checks
   */
  stopPeriodicChecks() {
    if (this._checkInterval) {
      clearInterval(this._checkInterval);
      this._checkInterval = null;
      console.log('Periodic update checks stopped');
    }
  }

  /**
   * Get cached update info
   * @returns {Object|null} Cached update info
   */
  getCachedInfo() {
    return this.checker.getCachedInfo();
  }

  /**
   * Clear all caches
   */
  clearCache() {
    this.checker.clearCache();
  }
}

module.exports = AutoUpdater;
