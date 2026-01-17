const { contextBridge, ipcRenderer } = require('electron');

// Expose a safe API to the renderer process
contextBridge.exposeInMainWorld('traceAPI', {
  // Ping the Electron main process (for testing IPC)
  ping: () => ipcRenderer.invoke('ping'),

  // Platform info
  platform: process.platform,

  // Python backend methods
  python: {
    // Check if Python backend is ready
    isReady: () => ipcRenderer.invoke('python:ready'),

    // Ping the Python backend
    ping: () => ipcRenderer.invoke('python:ping'),

    // Get Python backend status
    getStatus: () => ipcRenderer.invoke('python:status'),

    // Generic call to Python backend
    call: (method, params) => ipcRenderer.invoke('python:call', method, params),
  },
});
