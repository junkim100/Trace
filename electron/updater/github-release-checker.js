/**
 * GitHub Release Checker for Trace Auto-Updates
 *
 * Fetches latest release from GitHub Releases API and compares
 * with current version to detect available updates.
 */

const https = require('https');
const { app } = require('electron');

const GITHUB_OWNER = 'junkim100';
const GITHUB_REPO = 'Trace';
const CACHE_DURATION_MS = 15 * 60 * 1000; // 15 minutes

class GitHubReleaseChecker {
  constructor() {
    this._cache = null;
    this._lastCheck = 0;
  }

  /**
   * Check for available updates
   * @param {boolean} force - Bypass cache and force fresh check
   * @returns {Promise<Object>} Update info with available flag
   */
  async checkForUpdate(force = false) {
    // Return cached result if recent (unless forced)
    if (!force && this._cache && Date.now() - this._lastCheck < CACHE_DURATION_MS) {
      return this._cache;
    }

    try {
      const release = await this._fetchLatestRelease();

      if (!release) {
        return { available: false, error: 'Failed to fetch release info' };
      }

      // Skip draft and prerelease versions
      if (release.draft || release.prerelease) {
        return { available: false, reason: 'Latest release is draft/prerelease' };
      }

      const currentVersion = app.getVersion();
      const latestVersion = release.tag_name.replace(/^v/, '');

      const updateAvailable = this._isNewerVersion(latestVersion, currentVersion);

      const result = {
        available: updateAvailable,
        currentVersion,
        latestVersion,
        releaseUrl: release.html_url,
        releaseNotes: release.body || 'No release notes available.',
        publishedAt: release.published_at,
        releaseName: release.name,
        assets: this._filterMacAssets(release.assets || []),
      };

      this._cache = result;
      this._lastCheck = Date.now();
      return result;
    } catch (error) {
      console.error('GitHub release check failed:', error);
      return { available: false, error: error.message };
    }
  }

  /**
   * Compare semantic versions
   * @param {string} latest - Latest version string
   * @param {string} current - Current version string
   * @returns {boolean} True if latest is newer
   */
  _isNewerVersion(latest, current) {
    // Remove any pre-release suffix for comparison
    const latestClean = latest.split('-')[0];
    const currentClean = current.split('-')[0];

    const latestParts = latestClean.split('.').map(Number);
    const currentParts = currentClean.split('.').map(Number);

    // Pad arrays to same length
    while (latestParts.length < 3) latestParts.push(0);
    while (currentParts.length < 3) currentParts.push(0);

    for (let i = 0; i < 3; i++) {
      if (latestParts[i] > currentParts[i]) return true;
      if (latestParts[i] < currentParts[i]) return false;
    }
    return false;
  }

  /**
   * Filter assets to find macOS DMG for current architecture
   * @param {Array} assets - GitHub release assets
   * @returns {Array} Filtered assets for current platform
   */
  _filterMacAssets(assets) {
    const arch = process.arch; // 'x64' or 'arm64'

    return assets
      .filter(asset => {
        const name = asset.name.toLowerCase();
        // Look for DMG files
        if (!name.endsWith('.dmg')) return false;

        // Match architecture
        if (arch === 'arm64') {
          return name.includes('arm64') || name.includes('aarch64');
        } else {
          // x64 - match files without arm64 or explicit x64
          return !name.includes('arm64') && !name.includes('aarch64');
        }
      })
      .map(asset => ({
        name: asset.name,
        downloadUrl: asset.browser_download_url,
        size: asset.size,
        contentType: asset.content_type,
      }));
  }

  /**
   * Fetch latest release from GitHub API
   * @returns {Promise<Object|null>} Release object or null on failure
   */
  _fetchLatestRelease() {
    return new Promise((resolve, reject) => {
      const options = {
        hostname: 'api.github.com',
        path: `/repos/${GITHUB_OWNER}/${GITHUB_REPO}/releases/latest`,
        method: 'GET',
        headers: {
          'User-Agent': `Trace/${app.getVersion()}`,
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
              const release = JSON.parse(data);
              resolve(release);
            } catch (parseError) {
              reject(new Error('Failed to parse release data'));
            }
          } else if (res.statusCode === 404) {
            // No releases found
            resolve(null);
          } else if (res.statusCode === 403) {
            // Rate limited
            reject(new Error('GitHub API rate limit exceeded'));
          } else {
            reject(new Error(`GitHub API returned status ${res.statusCode}`));
          }
        });
      });

      req.on('error', (error) => {
        reject(error);
      });

      // Set timeout
      req.setTimeout(10000, () => {
        req.destroy();
        reject(new Error('Request timeout'));
      });

      req.end();
    });
  }

  /**
   * Get cached update info
   * @returns {Object|null} Cached update info or null
   */
  getCachedInfo() {
    return this._cache;
  }

  /**
   * Clear the cache
   */
  clearCache() {
    this._cache = null;
    this._lastCheck = 0;
  }
}

module.exports = GitHubReleaseChecker;
