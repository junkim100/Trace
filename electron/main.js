const { app, BrowserWindow, ipcMain } = require('electron');
const path = require('path');
const { spawn } = require('child_process');
const readline = require('readline');

let mainWindow = null;
let pythonProcess = null;
let pythonReady = false;
let pendingRequests = new Map(); // id -> { resolve, reject, timeout }
let requestId = 0;

// Get the path to the Python executable
function getPythonPath() {
  // For now, always use uv run from the project root
  // In a production build, we would bundle Python or use a different strategy
  // The project root is one level up from the electron directory
  const projectRoot = path.join(__dirname, '..');

  return {
    command: 'uv',
    args: ['run', 'trace', 'serve'],
    cwd: projectRoot,
  };
}

function startPythonBackend() {
  const { command, args, cwd } = getPythonPath();

  console.log(`Starting Python backend: ${command} ${args.join(' ')} in ${cwd}`);

  pythonProcess = spawn(command, args, {
    cwd,
    stdio: ['pipe', 'pipe', 'pipe'],
    env: { ...process.env, PYTHONUNBUFFERED: '1' },
  });

  // Create readline interface for reading JSON lines from stdout
  const rl = readline.createInterface({
    input: pythonProcess.stdout,
    crlfDelay: Infinity,
  });

  rl.on('line', (line) => {
    try {
      const message = JSON.parse(line);

      if (message.type === 'ready') {
        pythonReady = true;
        console.log(`Python backend ready (version ${message.version})`);
        return;
      }

      // Handle response to a pending request
      if (message.id && pendingRequests.has(message.id)) {
        const { resolve, reject, timeout } = pendingRequests.get(message.id);
        clearTimeout(timeout);
        pendingRequests.delete(message.id);

        if (message.success) {
          resolve(message.result);
        } else {
          reject(new Error(message.error || 'Unknown error'));
        }
      }
    } catch (err) {
      console.error('Failed to parse Python output:', line, err);
    }
  });

  // Log stderr for debugging
  pythonProcess.stderr.on('data', (data) => {
    console.error(`Python stderr: ${data}`);
  });

  pythonProcess.on('error', (err) => {
    console.error('Failed to start Python backend:', err);
    pythonReady = false;
  });

  pythonProcess.on('exit', (code, signal) => {
    console.log(`Python backend exited (code: ${code}, signal: ${signal})`);
    pythonReady = false;
    pythonProcess = null;

    // Reject all pending requests
    for (const [id, { reject, timeout }] of pendingRequests) {
      clearTimeout(timeout);
      reject(new Error('Python backend exited'));
    }
    pendingRequests.clear();
  });
}

function stopPythonBackend() {
  if (pythonProcess) {
    // Send shutdown command
    callPython('shutdown', {}).catch(() => {});

    // Give it a moment to shut down gracefully
    setTimeout(() => {
      if (pythonProcess) {
        pythonProcess.kill();
        pythonProcess = null;
      }
    }, 1000);
  }
}

function callPython(method, params = {}, timeoutMs = 30000) {
  return new Promise((resolve, reject) => {
    if (!pythonProcess || !pythonReady) {
      reject(new Error('Python backend not ready'));
      return;
    }

    const id = `req_${++requestId}`;
    const request = { id, method, params };

    const timeout = setTimeout(() => {
      if (pendingRequests.has(id)) {
        pendingRequests.delete(id);
        reject(new Error(`Request ${method} timed out`));
      }
    }, timeoutMs);

    pendingRequests.set(id, { resolve, reject, timeout });

    try {
      pythonProcess.stdin.write(JSON.stringify(request) + '\n');
    } catch (err) {
      clearTimeout(timeout);
      pendingRequests.delete(id);
      reject(err);
    }
  });
}

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1200,
    height: 800,
    minWidth: 800,
    minHeight: 600,
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
    },
    titleBarStyle: 'hiddenInset',
    vibrancy: 'under-window',
    visualEffectState: 'active',
    show: false,
  });

  // Load the app
  if (process.env.NODE_ENV === 'development') {
    mainWindow.loadURL('http://localhost:5173');
    mainWindow.webContents.openDevTools();
  } else {
    mainWindow.loadFile(path.join(__dirname, 'dist', 'index.html'));
  }

  // Show window when ready to prevent visual flash
  mainWindow.once('ready-to-show', () => {
    mainWindow.show();
  });

  mainWindow.on('closed', () => {
    mainWindow = null;
  });
}

// This method will be called when Electron has finished
// initialization and is ready to create browser windows.
app.whenReady().then(() => {
  // Start Python backend before creating window
  startPythonBackend();

  createWindow();

  app.on('activate', () => {
    // On macOS it's common to re-create a window in the app when the
    // dock icon is clicked and there are no other windows open.
    if (BrowserWindow.getAllWindows().length === 0) {
      createWindow();
    }
  });
});

// Quit when all windows are closed, except on macOS.
app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') {
    app.quit();
  }
});

app.on('before-quit', () => {
  stopPythonBackend();
});

// IPC handlers for renderer process
ipcMain.handle('ping', async () => {
  return 'pong';
});

// Python backend proxy handlers
ipcMain.handle('python:ping', async () => {
  return callPython('ping');
});

ipcMain.handle('python:status', async () => {
  return callPython('get_status');
});

ipcMain.handle('python:ready', async () => {
  return pythonReady;
});

// Generic Python call handler
ipcMain.handle('python:call', async (event, method, params) => {
  return callPython(method, params);
});
