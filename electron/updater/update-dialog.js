/**
 * Update Dialog UI for Trace Auto-Updates
 *
 * Handles native dialog prompts for update notifications
 * and user interaction with update options.
 */

const { dialog, shell, Notification } = require('electron');

/**
 * Truncate release notes for dialog display
 * @param {string} notes - Full release notes
 * @param {number} maxLength - Maximum length
 * @returns {string} Truncated notes
 */
function truncateNotes(notes, maxLength = 500) {
  if (!notes) return 'No release notes available.';
  if (notes.length <= maxLength) return notes;
  return notes.substring(0, maxLength) + '...';
}

/**
 * Format file size for display
 * @param {number} bytes - Size in bytes
 * @returns {string} Formatted size string
 */
function formatSize(bytes) {
  if (!bytes) return '';
  const mb = bytes / (1024 * 1024);
  return `${mb.toFixed(1)} MB`;
}

/**
 * Show update available dialog
 * @param {BrowserWindow} mainWindow - Main application window
 * @param {Object} updateInfo - Update information from checker
 * @returns {Promise<Object>} User's chosen action
 */
async function showUpdateDialog(mainWindow, updateInfo) {
  const assetInfo = updateInfo.assets?.[0];
  const sizeInfo = assetInfo ? ` (${formatSize(assetInfo.size)})` : '';

  const detail = [
    `Current version: ${updateInfo.currentVersion}`,
    `New version: ${updateInfo.latestVersion}${sizeInfo}`,
    '',
    'Release notes:',
    truncateNotes(updateInfo.releaseNotes, 400),
  ].join('\n');

  const response = await dialog.showMessageBox(mainWindow, {
    type: 'info',
    title: 'Update Available',
    message: `A new version of Trace is available!`,
    detail,
    buttons: ['Download', 'Remind Me Later', 'Skip This Version'],
    defaultId: 0,
    cancelId: 1,
    noLink: true,
  });

  const actions = ['download', 'later', 'skip'];
  return {
    action: actions[response.response],
    version: updateInfo.latestVersion,
  };
}

/**
 * Show "no update available" dialog
 * @param {BrowserWindow} mainWindow - Main application window
 * @param {string} currentVersion - Current app version
 */
async function showNoUpdateDialog(mainWindow, currentVersion) {
  await dialog.showMessageBox(mainWindow, {
    type: 'info',
    title: 'No Updates Available',
    message: 'You are running the latest version!',
    detail: `Current version: ${currentVersion}`,
    buttons: ['OK'],
  });
}

/**
 * Show update check error dialog
 * @param {BrowserWindow} mainWindow - Main application window
 * @param {string} errorMessage - Error message
 */
async function showUpdateErrorDialog(mainWindow, errorMessage) {
  await dialog.showMessageBox(mainWindow, {
    type: 'error',
    title: 'Update Check Failed',
    message: 'Could not check for updates',
    detail: errorMessage || 'Please check your internet connection and try again.',
    buttons: ['OK'],
  });
}

/**
 * Open release page in default browser
 * @param {string} releaseUrl - GitHub release URL
 */
function openReleasePage(releaseUrl) {
  shell.openExternal(releaseUrl);
}

/**
 * Open direct download link in default browser
 * @param {string} downloadUrl - Direct download URL
 */
function openDownloadLink(downloadUrl) {
  shell.openExternal(downloadUrl);
}

/**
 * Show system notification for available update
 * @param {Object} updateInfo - Update information
 * @returns {Notification} The notification object
 */
function showUpdateNotification(updateInfo) {
  const notification = new Notification({
    title: 'Trace Update Available',
    body: `Version ${updateInfo.latestVersion} is ready to download`,
    silent: false,
  });

  notification.on('click', () => {
    openReleasePage(updateInfo.releaseUrl);
  });

  notification.show();
  return notification;
}

module.exports = {
  showUpdateDialog,
  showNoUpdateDialog,
  showUpdateErrorDialog,
  openReleasePage,
  openDownloadLink,
  showUpdateNotification,
  truncateNotes,
  formatSize,
};
