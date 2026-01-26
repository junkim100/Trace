/**
 * Auto-updater module for Trace
 * Checks GitHub releases for updates and notifies the user
 */

const { app } = require('electron');
const https = require('https');

// GitHub repository info
const GITHUB_OWNER = 'junkim100';
const GITHUB_REPO = 'Trace';
const RELEASES_URL = `https://api.github.com/repos/${GITHUB_OWNER}/${GITHUB_REPO}/releases/latest`;

class AutoUpdater {
  constructor(options = {}) {
    this.pythonCall = options.pythonCall;
    this.mainWindow = null;
    this.cachedInfo = null;
    this.settings = {
      check_on_launch: true,
      check_periodically: true,
      check_interval_hours: 24,
      skipped_versions: [],
      last_check_timestamp: null,
      remind_later_until: null,
    };
    this.checkInterval = null;
  }

  setMainWindow(window) {
    this.mainWindow = window;
  }

  async initialize() {
    // Load settings from config
    await this.loadSettings();

    // Check on launch if enabled
    if (this.settings.check_on_launch) {
      // Delay initial check to let app fully load
      setTimeout(() => {
        this.checkForUpdates({ silent: true });
      }, 5000);
    }

    // Set up periodic checks if enabled
    if (this.settings.check_periodically && this.settings.check_interval_hours > 0) {
      const intervalMs = this.settings.check_interval_hours * 60 * 60 * 1000;
      this.checkInterval = setInterval(() => {
        this.checkForUpdates({ silent: true });
      }, intervalMs);
    }
  }

  async loadSettings() {
    try {
      if (this.pythonCall) {
        const result = await this.pythonCall('settings.get_value', { key: 'updates' });
        if (result && typeof result === 'object') {
          this.settings = { ...this.settings, ...result };
        }
      }
    } catch (err) {
      console.error('Failed to load update settings:', err);
    }
  }

  async saveSettings() {
    try {
      if (this.pythonCall) {
        await this.pythonCall('settings.set_value', {
          key: 'updates',
          value: this.settings,
        });
      }
    } catch (err) {
      console.error('Failed to save update settings:', err);
    }
  }

  getCurrentVersion() {
    return app.getVersion();
  }

  async checkForUpdates(options = {}) {
    const { silent = false, force = false } = options;
    const currentVersion = this.getCurrentVersion();

    // Check if we should skip this check
    if (!force) {
      // Check remind later
      if (this.settings.remind_later_until && Date.now() < this.settings.remind_later_until) {
        return {
          checked: false,
          skipped: true,
          reason: 'Remind later active',
          currentVersion,
        };
      }

      // Check last check time (don't check more than once per hour unless forced)
      if (this.settings.last_check_timestamp) {
        const hoursSinceLastCheck = (Date.now() - this.settings.last_check_timestamp) / (1000 * 60 * 60);
        if (hoursSinceLastCheck < 1) {
          return {
            checked: false,
            skipped: true,
            reason: 'Checked recently',
            currentVersion,
            updateInfo: this.cachedInfo,
          };
        }
      }
    }

    try {
      const releaseInfo = await this.fetchLatestRelease();

      // Update last check timestamp
      this.settings.last_check_timestamp = Date.now();
      await this.saveSettings();

      if (!releaseInfo) {
        return {
          checked: true,
          available: false,
          currentVersion,
          error: 'Could not fetch release info',
        };
      }

      const latestVersion = releaseInfo.tag_name.replace(/^v/, '');
      const isNewer = this.isNewerVersion(latestVersion, currentVersion);
      const isSkipped = this.settings.skipped_versions.includes(latestVersion);

      // Build update info
      const updateInfo = {
        available: isNewer && !isSkipped,
        currentVersion,
        latestVersion,
        releaseUrl: releaseInfo.html_url,
        releaseNotes: releaseInfo.body || '',
        releaseName: releaseInfo.name,
        publishedAt: releaseInfo.published_at,
        assets: (releaseInfo.assets || []).map(asset => ({
          name: asset.name,
          downloadUrl: asset.browser_download_url,
          size: asset.size,
          contentType: asset.content_type,
        })),
      };

      // Cache the info
      this.cachedInfo = updateInfo;

      // Notify window if update available and not silent
      if (updateInfo.available && !silent && this.mainWindow) {
        this.mainWindow.webContents.send('updates:available', updateInfo);
      }

      return {
        checked: true,
        available: updateInfo.available,
        currentVersion,
        updateInfo,
      };

    } catch (err) {
      console.error('Update check failed:', err);
      return {
        checked: true,
        available: false,
        currentVersion,
        error: err.message,
      };
    }
  }

  fetchLatestRelease() {
    return new Promise((resolve, reject) => {
      const options = {
        hostname: 'api.github.com',
        path: `/repos/${GITHUB_OWNER}/${GITHUB_REPO}/releases/latest`,
        method: 'GET',
        headers: {
          'User-Agent': `Trace/${this.getCurrentVersion()}`,
          'Accept': 'application/vnd.github.v3+json',
        },
      };

      const req = https.request(options, (res) => {
        let data = '';

        res.on('data', (chunk) => {
          data += chunk;
        });

        res.on('end', () => {
          if (res.statusCode === 200) {
            try {
              resolve(JSON.parse(data));
            } catch (e) {
              reject(new Error('Invalid JSON response'));
            }
          } else if (res.statusCode === 404) {
            // No releases yet
            resolve(null);
          } else {
            reject(new Error(`HTTP ${res.statusCode}`));
          }
        });
      });

      req.on('error', reject);
      req.setTimeout(10000, () => {
        req.destroy();
        reject(new Error('Request timeout'));
      });

      req.end();
    });
  }

  isNewerVersion(latest, current) {
    const latestParts = latest.split('.').map(Number);
    const currentParts = current.split('.').map(Number);

    for (let i = 0; i < Math.max(latestParts.length, currentParts.length); i++) {
      const l = latestParts[i] || 0;
      const c = currentParts[i] || 0;
      if (l > c) return true;
      if (l < c) return false;
    }
    return false;
  }

  getCachedInfo() {
    return this.cachedInfo;
  }

  skipVersion(version) {
    if (!this.settings.skipped_versions.includes(version)) {
      this.settings.skipped_versions.push(version);
      this.saveSettings();
    }
  }

  remindLater(hours = 24) {
    this.settings.remind_later_until = Date.now() + (hours * 60 * 60 * 1000);
    this.saveSettings();
  }

  destroy() {
    if (this.checkInterval) {
      clearInterval(this.checkInterval);
      this.checkInterval = null;
    }
  }
}

module.exports = AutoUpdater;
