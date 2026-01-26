/**
 * Update Settings Manager for Trace Auto-Updates
 *
 * Manages persistence of update-related settings including
 * skipped versions and reminder preferences.
 */

class UpdateSettings {
  /**
   * Create update settings manager
   * @param {Function} pythonCallFn - Function to call Python backend
   */
  constructor(pythonCallFn) {
    this._call = pythonCallFn;
    this._cache = null;
  }

  /**
   * Get all update settings
   * @returns {Promise<Object>} Update settings object
   */
  async getSettings() {
    try {
      const result = await this._call('settings.get_value', { key: 'updates' });
      this._cache = result || this._getDefaults();
      return this._cache;
    } catch (error) {
      console.error('Failed to get update settings:', error);
      return this._getDefaults();
    }
  }

  /**
   * Get default settings
   * @returns {Object} Default settings object
   */
  _getDefaults() {
    return {
      check_on_launch: true,
      check_periodically: true,
      check_interval_hours: 24,
      skipped_versions: [],
      last_check_timestamp: null,
      remind_later_until: null,
    };
  }

  /**
   * Set whether to check for updates on launch
   * @param {boolean} enabled - Enable or disable
   */
  async setCheckOnLaunch(enabled) {
    try {
      await this._call('settings.set_value', {
        key: 'updates.check_on_launch',
        value: enabled,
      });
      if (this._cache) this._cache.check_on_launch = enabled;
    } catch (error) {
      console.error('Failed to set check_on_launch:', error);
    }
  }

  /**
   * Set whether to check periodically
   * @param {boolean} enabled - Enable or disable
   */
  async setCheckPeriodically(enabled) {
    try {
      await this._call('settings.set_value', {
        key: 'updates.check_periodically',
        value: enabled,
      });
      if (this._cache) this._cache.check_periodically = enabled;
    } catch (error) {
      console.error('Failed to set check_periodically:', error);
    }
  }

  /**
   * Add a version to the skip list
   * @param {string} version - Version to skip
   */
  async skipVersion(version) {
    try {
      const settings = await this.getSettings();
      const skipped = settings.skipped_versions || [];

      if (!skipped.includes(version)) {
        skipped.push(version);
        await this._call('settings.set_value', {
          key: 'updates.skipped_versions',
          value: skipped,
        });
        if (this._cache) this._cache.skipped_versions = skipped;
      }
    } catch (error) {
      console.error('Failed to skip version:', error);
    }
  }

  /**
   * Check if a version is skipped
   * @param {string} version - Version to check
   * @returns {Promise<boolean>} True if version is skipped
   */
  async isVersionSkipped(version) {
    try {
      const settings = await this.getSettings();
      return (settings.skipped_versions || []).includes(version);
    } catch (error) {
      console.error('Failed to check skipped version:', error);
      return false;
    }
  }

  /**
   * Clear skipped versions list
   */
  async clearSkippedVersions() {
    try {
      await this._call('settings.set_value', {
        key: 'updates.skipped_versions',
        value: [],
      });
      if (this._cache) this._cache.skipped_versions = [];
    } catch (error) {
      console.error('Failed to clear skipped versions:', error);
    }
  }

  /**
   * Set remind later timestamp
   * @param {number} hours - Hours to wait before reminding
   */
  async setRemindLater(hours = 24) {
    try {
      const until = Date.now() + hours * 60 * 60 * 1000;
      await this._call('settings.set_value', {
        key: 'updates.remind_later_until',
        value: until,
      });
      if (this._cache) this._cache.remind_later_until = until;
    } catch (error) {
      console.error('Failed to set remind later:', error);
    }
  }

  /**
   * Check if we should remind later
   * @returns {Promise<boolean>} True if reminder is still active
   */
  async shouldRemindLater() {
    try {
      const settings = await this.getSettings();
      const until = settings.remind_later_until;
      return until && until > Date.now();
    } catch (error) {
      return false;
    }
  }

  /**
   * Clear remind later timestamp
   */
  async clearRemindLater() {
    try {
      await this._call('settings.set_value', {
        key: 'updates.remind_later_until',
        value: null,
      });
      if (this._cache) this._cache.remind_later_until = null;
    } catch (error) {
      console.error('Failed to clear remind later:', error);
    }
  }

  /**
   * Update last check timestamp
   */
  async updateLastCheckTimestamp() {
    try {
      const now = Date.now();
      await this._call('settings.set_value', {
        key: 'updates.last_check_timestamp',
        value: now,
      });
      if (this._cache) this._cache.last_check_timestamp = now;
    } catch (error) {
      console.error('Failed to update last check timestamp:', error);
    }
  }
}

module.exports = UpdateSettings;
